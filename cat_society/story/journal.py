"""Story journal with Soundbook, commission, team and shop tabs."""

import pygame

from .. import ui
from ..components import catalog
from ..ui.icons import draw_icon
from ..screens.soundbook import SoundbookOverlay
from .decorations import definition as decor_definition
from .economy import UPGRADES
from .helpers import HELPER_INFO


class StoryJournalOverlay:
    TABS = ("SOUNDS", "MISSIONS", "TEAM", "SHOP")

    def __init__(self, app, screen):
        self.app = app
        self.screen = screen
        self.soundbook = SoundbookOverlay(app)
        self.tab = 1
        self.idx = 0
        self.rows = []
        self.buttons = []
        self.message = ""
        self.message_t = 0.0

    def reset(self):
        self.soundbook.reset()
        self.tab = 1
        self.idx = 0
        self.rows = []
        self.buttons = []
        self.message = ""
        self.message_t = 0.0

    def _set_tab(self, value):
        self.tab = value % len(self.TABS)
        self.idx = 0
        self.rows = []
        self.buttons = []

    def update(self, dt):
        self.message_t = max(0.0, self.message_t - dt)

    def _mission_rows(self):
        st = self.screen.story_state
        rows = []
        for lead in st.commission_inbox:
            rows.append(("lead", lead))
        for order in sorted(st.active_orders, key=lambda x: float(x.get("due", 0))):
            rows.append(("active", order))
        for rec in reversed(st.history[-20:]):
            rows.append(("history", rec))
        return rows

    def _team_rows(self):
        manager = self.screen.helpers
        return [("helper", kind) for kind in ("assistant", "scout", "courier")
                if manager is not None and manager.hired(kind)]

    def _shop_rows(self):
        st = self.screen.story_state
        rows = []
        for item_id, count in sorted(st.decorations_owned.items()):
            available = self.screen.decorations.inventory_count(item_id)
            if count > 0:
                rows.append(("decor", {"id": item_id, "owned": count, "available": available}))
        for key, enabled in sorted(st.upgrades.items()):
            if enabled:
                rows.append(("upgrade", key))
        return rows

    def current_rows(self):
        if self.tab == 1:
            return self._mission_rows()
        if self.tab == 2:
            return self._team_rows()
        if self.tab == 3:
            return self._shop_rows()
        return []

    def _flash(self, text):
        self.message = text
        self.message_t = 4.0

    def _mission_action(self, action):
        rows = self._mission_rows()
        if not rows:
            return
        self.idx = max(0, min(self.idx, len(rows)-1))
        kind, rec = rows[self.idx]
        if kind == "lead":
            if action == "primary":
                order, text = self.screen.clients.accept_lead(self.screen, rec)
                self._flash(text)
                if order is not None and (order.get("request") or {}).get("service") in ("plant", "gramophone"):
                    self.screen._prepare_order(order, None)
                    self.screen._set_paused(False)
            elif action == "secondary":
                self.screen.clients.decline_lead(rec)
                self._flash("Request declined. No reputation was lost.")
        elif kind == "active":
            if action == "primary":
                if rec.get("status") == "delivery":
                    if self.screen.field_delivery and self.screen.field_delivery.get("order_id") == rec.get("id"):
                        self._flash("This delivery is ready. Follow the gold marker or use the courier.")
                    else:
                        self.screen._prepare_order(rec, None)
                        self.screen._set_paused(False)
                else:
                    self._flash("The client will return. You can compose the music before then.")
            elif action == "secondary":
                ok, text = self.screen.assign_courier(rec)
                self._flash(text)
                if ok:
                    self.idx = max(0, self.idx-1)
        elif kind == "history":
            self._flash("Completed on day %s. %s coins earned." %
                        (rec.get("day", "?"), rec.get("coins", 0)))

    def _team_action(self, action):
        rows = self._team_rows()
        if not rows:
            self._flash("Bal has not hired anyone yet. Check the travelling merchant.")
            return
        kind = rows[max(0, min(self.idx, len(rows)-1))][1]
        manager = self.screen.helpers
        if action == "primary":
            manager.toggle_schedule(kind)
            rec = manager.record(kind)
            self._flash("%s is %s for the next work day." %
                        (HELPER_INFO[kind]["name"], "scheduled" if rec.get("scheduled") else "taking the day off"))
        elif action == "secondary" and kind == "scout":
            region = manager.cycle_scout_region(1)
            self._flash("%s will search the %s." % (HELPER_INFO["scout"]["name"], region))

    def _shop_action(self, action):
        rows = self._shop_rows()
        if not rows:
            return
        kind, rec = rows[max(0, min(self.idx, len(rows)-1))]
        if kind == "decor" and action == "primary":
            if rec["available"] <= 0:
                self._flash("Every copy is already placed. Remove one in the world first.")
                return
            if self.screen.decorations.begin(rec["id"]):
                self.screen._set_paused(False)
                self.screen._toast = "Decoration mode: E place, R rotate, Q cancel."
                self.screen._toast_t = 4.0
        elif kind == "upgrade":
            self._flash("This shop upgrade is installed and active.")

    def _action(self, action):
        if self.tab == 1:
            self._mission_action(action)
        elif self.tab == 2:
            self._team_action(action)
        elif self.tab == 3:
            self._shop_action(action)

    def handle_event(self, e, close):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                close(); return True
            if e.key in (pygame.K_LEFT, pygame.K_a):
                self._set_tab(self.tab-1); return True
            if e.key in (pygame.K_RIGHT, pygame.K_d):
                self._set_tab(self.tab+1); return True
            if self.tab == 0:
                return self.soundbook.handle_event(e, close)
            rows = self.current_rows()
            if e.key in (pygame.K_UP, pygame.K_w):
                self.idx = max(0, self.idx-1); return True
            if e.key in (pygame.K_DOWN, pygame.K_s):
                self.idx = min(max(0, len(rows)-1), self.idx+1); return True
            if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._action("primary"); return True
            if e.key in (pygame.K_x, pygame.K_BACKSPACE):
                self._action("secondary"); return True
        if e.type == pygame.MOUSEWHEEL and self.tab != 0:
            rows = self.current_rows()
            self.idx = max(0, min(max(0, len(rows)-1), self.idx-e.y)); return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, action, value in self.buttons:
                if not rect.collidepoint(e.pos):
                    continue
                if action == "tab": self._set_tab(value)
                elif action == "row": self.idx = value
                elif action == "primary": self._action("primary")
                elif action == "secondary": self._action("secondary")
                return True
        if self.tab == 0:
            return self.soundbook.handle_event(e, close)
        return True

    def draw(self, surf):
        if self.tab == 0:
            self.buttons = []
            self.soundbook.draw(surf)
            self._draw_tabs(surf)
            return
        w,h=surf.get_size(); S=lambda v:ui.scaled(h,v)
        veil=pygame.Surface((w,h),pygame.SRCALPHA); veil.fill((24,22,20,190)); surf.blit(veil,(0,0))
        panel=pygame.Rect(int(w*.045),int(h*.045),int(w*.91),int(h*.91)); ui.draw_panel(surf,panel,fill=ui.PAPER,radius=S(16))
        self.buttons=[]
        self._draw_tabs(surf,panel)
        if self.tab==1: self._draw_missions(surf,panel)
        elif self.tab==2: self._draw_team(surf,panel)
        else: self._draw_shop(surf,panel)

    def _draw_tabs(self,surf,panel=None):
        w,h=surf.get_size(); S=lambda v:ui.scaled(h,v)
        if panel is None:
            panel=pygame.Rect(int(w*.055),int(h*.055),int(w*.89),int(h*.89))
        total=S(520); x=panel.centerx-total//2; y=panel.y+S(16); gap=S(7); tw=(total-gap*3)//4
        for i,label in enumerate(self.TABS):
            r=pygame.Rect(x+i*(tw+gap),y,tw,S(38)); selected=i==self.tab
            ui.draw_panel(surf,r,fill=ui.CREAM if selected else ui.PAPER_DK,edge=ui.GRASS if selected else ui.PAPER_EDGE,radius=S(8),shadow=False)
            ui.pixel_text_center_box(surf,label,S(13),r,color=ui.INK)
            self.buttons.append((r,"tab",i))
        ui.pixel_text(surf,"LEFT / RIGHT TABS   ESC BACK",S(11),panel.right-S(24),panel.y+S(61),color=ui.INK_SOFT,right=True)

    def _base(self,surf,panel,title,subtitle):
        h=surf.get_height(); S=lambda v:ui.scaled(h,v)
        ui.pixel_text(surf,title,S(25),panel.x+S(28),panel.y+S(72),color=ui.INK)
        ui.pixel_text_fit_box(surf,subtitle,S(13),pygame.Rect(panel.x+S(28),panel.y+S(108),panel.w-S(56),S(24)),color=ui.INK_SOFT,min_size=S(10),bold=False,center=False)
        return pygame.Rect(panel.x+S(24),panel.y+S(145),panel.w-S(48),panel.h-S(235))

    def _draw_missions(self,surf,panel):
        h=surf.get_height(); S=lambda v:ui.scaled(h,v)
        area=self._base(surf,panel,"COMMISSIONS","Clover's notes are offers, not accepted jobs. Active missions have real deadlines.")
        rows=self._mission_rows(); self.idx=max(0,min(self.idx,max(0,len(rows)-1)))
        row_h=S(66); visible=max(1,area.h//row_h); first=max(0,min(self.idx-visible//2,max(0,len(rows)-visible)))
        self.rows=[]
        for j,i in enumerate(range(first,min(len(rows),first+visible))):
            kind,rec=rows[i]; r=pygame.Rect(area.x,area.y+j*row_h,area.w,row_h-S(7)); selected=i==self.idx
            edge=(207,157,83) if kind=="lead" else (ui.GRASS if kind=="active" else ui.PAPER_EDGE)
            ui.draw_panel(surf,r,fill=ui.CREAM if selected else ui.PAPER_DK,edge=edge,radius=S(9),shadow=False)
            tag={"lead":"NEW OFFER","active":"ACTIVE","history":"DONE"}[kind]
            ui.pixel_text(surf,tag,S(11),r.x+S(14),r.y+S(9),color=edge)
            if kind=="history":
                title="%s - %s"%(rec.get("client","Client"),rec.get("title","Commission")); detail="Day %s   %s coins   %s"%(rec.get("day","?"),rec.get("coins",0),rec.get("item",""))
            else:
                req=rec.get("request") or {}; title="%s - %s"%(rec.get("name","Client"),req.get("title","Commission")); detail=self._request_line(req)
                if kind=="active": detail += "   Due: %s"%self._due_text(rec)
                else: detail += "   Offer valid: %s"%self._offer_due_text(rec)
            ui.pixel_text_fit_box(surf,title,S(15),pygame.Rect(r.x+S(104),r.y+S(7),r.w-S(122),S(22)),color=ui.INK,min_size=S(10),center=False)
            ui.pixel_text_fit_box(surf,detail,S(11),pygame.Rect(r.x+S(14),r.y+S(35),r.w-S(28),S(17)),color=ui.INK_SOFT,min_size=S(8),bold=False,center=False)
            self.buttons.append((r,"row",i))
        if not rows: ui.pixel_text(surf,"No commissions yet. New requests will appear here.",S(18),area.centerx,area.centery,color=ui.INK_SOFT,center=True)
        primary="OPEN"; secondary=""
        if rows:
            kind,rec=rows[self.idx]
            if kind=="lead": primary="ACCEPT"; secondary="DECLINE"
            elif kind=="active":
                primary="PREPARE" if rec.get("status")=="delivery" else "DETAILS"
                if self.screen.helpers.can_courier(rec): secondary="SEND COURIER"
            else: primary="DETAILS"
        self._footer_buttons(surf,panel,primary,secondary)

    def _request_line(self,req):
        if req.get("kind")=="song":
            lo,hi=req.get("tempo",(80,120)); return "%s song, %d-%d BPM, needs %s"%(req.get("primary","warm"),lo,hi," and ".join(req.get("needs",("melody",))))
        return "%s %s seed from %s"%(req.get("primary","warm"),req.get("want_type","note"),req.get("region","meadow"))

    def _due_text(self,order):
        mins=max(0,int(float(order.get("due",0))-self.screen.clock.stamp+.5)); return "%dh %02dm"%(mins//60,mins%60)

    def _offer_due_text(self,lead):
        mins=max(0,int(float(lead.get("offer_due",0))-self.screen.clock.stamp+.5)); return "%dh %02dm"%(mins//60,mins%60)

    def _draw_team(self,surf,panel):
        h=surf.get_height(); S=lambda v:ui.scaled(h,v)
        area=self._base(surf,panel,"BAL'S TEAM","Only hired helpers appear here. They are paid only on scheduled work days and never compose for Bal.")
        rows=self._team_rows()
        if not rows:
            self.idx=0
            ui.pixel_text(surf,"Bal has not hired any helpers yet.",S(18),area.centerx,area.centery-S(16),color=ui.INK,center=True)
            ui.pixel_text(surf,"Recruit animals from Poko's travelling cart.",S(13),area.centerx,area.centery+S(18),color=ui.INK_SOFT,center=True)
            ui.pixel_text(surf,"No wages are charged until Bal hires someone.",S(11),panel.right-S(28),panel.bottom-S(42),color=ui.INK_SOFT,right=True)
            return
        self.idx=max(0,min(self.idx,len(rows)-1))
        row_h=max(S(56),min(S(72),(area.h-S(76))//max(1,len(rows))))
        row_step=row_h+S(6)
        for i,(_,kind) in enumerate(rows):
            info=HELPER_INFO[kind]; rec=self.screen.helpers.record(kind); r=pygame.Rect(area.x,area.y+i*row_step,area.w,row_h); selected=i==self.idx
            ui.draw_panel(surf,r,fill=ui.CREAM if selected else ui.PAPER_DK,edge=ui.GRASS if selected else ui.PAPER_EDGE,radius=S(10),shadow=False)
            draw_icon(surf,r.x+S(30),r.centery,S(14),(165,132,105),"note",0.0)
            if rec.get("on_duty"):
                status="WORKING TODAY"
                if rec.get("scheduled"):
                    status += " / BOOKED TOMORROW"
            else:
                status="BOOKED FOR NEXT DAY" if rec.get("scheduled") else "AVAILABLE"
            title="%s THE %s - %s"%(info["name"].upper(),info["species"].upper(),info["role"].upper())
            ui.pixel_text_fit_box(surf,title,S(16),pygame.Rect(r.x+S(56),r.y+S(8),r.w-S(72),S(21)),color=ui.INK,min_size=S(10),center=False)
            extra="%s   Wage %d coins"%(status,int(rec.get("wage",info["wage"])))
            if kind=="scout": extra += "   Region: %s"%rec.get("region","meadow")
            ui.pixel_text_fit_box(surf,extra,S(11),pygame.Rect(r.x+S(56),r.bottom-S(25),r.w-S(72),S(17)),color=ui.INK_SOFT,min_size=S(8),bold=False,center=False)
            self.buttons.append((r,"row",i))
        reports=self.screen.story_state.helper_reports[-2:]
        y=area.y+row_step*len(rows)+S(5); ui.pixel_text(surf,"RECENT REPORTS",S(13),area.x,y,color=ui.GRASS_DK)
        for rec in reversed(reports):
            y+=S(22); ui.pixel_text_fit_box(surf,rec.get("text",""),S(10),pygame.Rect(area.x,y,area.w,S(16)),color=ui.INK_SOFT,min_size=S(8),bold=False,center=False)
        selected_kind=rows[self.idx][1]
        selected_rec=self.screen.helpers.record(selected_kind)
        primary=("CANCEL NEXT DAY" if selected_rec.get("scheduled") else "BOOK NEXT DAY")
        sec="CHANGE REGION" if selected_kind=="scout" else ""
        self._footer_buttons(surf,panel,primary,sec)

    def _draw_shop(self,surf,panel):
        h=surf.get_height(); S=lambda v:ui.scaled(h,v)
        area=self._base(surf,panel,"SHOP AND DECORATIONS","Buy items from Poko, then place decorations around Bal's shop.")
        rows=self._shop_rows(); self.idx=max(0,min(self.idx,max(0,len(rows)-1)))
        row_h=S(59); visible=max(1,area.h//row_h); first=max(0,min(self.idx-visible//2,max(0,len(rows)-visible)))
        for j,i in enumerate(range(first,min(len(rows),first+visible))):
            kind,rec=rows[i]; r=pygame.Rect(area.x,area.y+j*row_h,area.w,row_h-S(6)); sel=i==self.idx
            ui.draw_panel(surf,r,fill=ui.CREAM if sel else ui.PAPER_DK,edge=ui.GRASS if sel else ui.PAPER_EDGE,radius=S(9),shadow=False)
            if kind=="decor":
                item=decor_definition(rec["id"]); title=item["name"]; detail="%d owned, %d ready to place. %s"%(rec["owned"],rec["available"],item["desc"])
            else:
                upgrade=UPGRADES.get(rec,{})
                title=upgrade.get("name",rec.replace("_"," ").title())
                detail=upgrade.get("desc","Installed shop upgrade")
            ui.pixel_text_fit_box(surf,title.upper(),S(14),pygame.Rect(r.x+S(16),r.y+S(7),r.w-S(32),S(20)),color=ui.INK,min_size=S(10),center=False)
            ui.pixel_text_fit_box(surf,detail,S(11),pygame.Rect(r.x+S(16),r.y+S(29),r.w-S(32),S(17)),color=ui.INK_SOFT,min_size=S(8),bold=False,center=False)
            self.buttons.append((r,"row",i))
        if not rows: ui.pixel_text(surf,"The shop storage is empty. Visit Poko's cart.",S(18),area.centerx,area.centery,color=ui.INK_SOFT,center=True)
        self._footer_buttons(surf,panel,"PLACE" if rows and rows[self.idx][0]=="decor" else "DETAILS","")

    def _footer_buttons(self,surf,panel,primary,secondary):
        h=surf.get_height(); S=lambda v:ui.scaled(h,v)
        if self.message_t>0:
            ui.pixel_text_fit_box(surf,self.message,S(12),pygame.Rect(panel.x+S(28),panel.bottom-S(73),panel.w-S(360),S(42)),color=ui.INK_SOFT,min_size=S(9),bold=False,center=False)
        x=panel.right-S(28); buttons=[]
        if secondary:
            w=S(150); r=pygame.Rect(x-w,panel.bottom-S(66),w,S(42)); x=r.x-S(10); buttons.append((r,secondary,"secondary",ui.PAPER_DK))
        w=S(142); r=pygame.Rect(x-w,panel.bottom-S(66),w,S(42)); buttons.append((r,primary,"primary",ui.GRASS))
        for rect,label,action,fill in buttons:
            ui.draw_panel(surf,rect,fill=fill,edge=ui.GRASS_DK if action=="primary" else ui.PAPER_EDGE,radius=S(8),shadow=False)
            ui.pixel_text_center_box(surf,label,S(12),rect,color=ui.CREAM if action=="primary" else ui.INK)
            self.buttons.append((rect,action,None))
