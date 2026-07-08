import sys
import os
import random
from enum import Enum, auto
from PyQt6.QtWidgets import QApplication, QLabel, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QMovie, QAction, QPixmap, QPainter


def resource_path(relative_path):
    """Resolve asset paths for both dev and PyInstaller bundle."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GRAVITY             = 1
MAX_FALL_SPEED      = 20
FLOOR_MARGIN        = 90
PHYSICS_INTERVAL_MS = 25        # ~60 fps
WALK_SPEED          = 1         # px per frame while walking
PAUSE_INTERVAL_MIN  = 2000      # ms — min time walking before a random pause
PAUSE_INTERVAL_MAX  = 10000      # ms — max time walking before a random pause
IDLE_DURATION_MIN   = 2000      # ms — min duration of each idle pause
IDLE_DURATION_MAX   = 20000      # ms — max duration of each idle pause
STUMBLE_INTERVAL_MIN = 10000     # ms — min time walking before a random stumble
STUMBLE_INTERVAL_MAX = 100000     # ms — max time walking before a random stumble
PET_SIZE            = 80
SPRITE_MARGIN       = 80        # transparent padding inside the GIF on each side
                                # tune this until the pet walks to the visible screen edge
PET_START_X         = 300
PET_START_Y         = 300

# GIF animations (QMovie)
ANIMATION_MAP = {
    "idle":          resource_path("assets/idle_left.gif"),
    "idle_left":     resource_path("assets/idle_left.gif"),
    "idle_right":    resource_path("assets/idle_right.gif"),
    "walk_to_left":  resource_path("assets/walk_to_left.gif"),
    "walk_to_right": resource_path("assets/walk_to_right.gif"),
    "falling":       resource_path("assets/fall_left.gif"),
    "fall_left":     resource_path("assets/fall_left.gif"),
    "fall_right":    resource_path("assets/fall_right.gif"),
    "die":           resource_path("assets/die.gif"),
    "dragged":       resource_path("assets/drag.gif"),
    "dropped":       resource_path("assets/drop.gif"),
}

# Static images (QPixmap)
STATIC_MAP = {
    "dragged": resource_path("assets/drag.png"),
    "dropped": resource_path("assets/drop.png"),
}

FALLBACK_ANIMATION = "walk_to_right"


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------
class PetState(Enum):
    IDLE         = auto()
    WALK_LEFT    = auto()
    WALK_RIGHT   = auto()
    FALLING      = auto()   # normal gravity fall (no drag)
    DRAGGED      = auto()   # held by mouse → drag.png
    DROPPED      = auto()   # released mid-air → drop.png until grounded
    LANDING      = auto()   # just hit the ground → fall.gif plays once
    DYING        = auto()   # die.gif plays once → quit
    PAUSED       = auto()   # standing still, playing idle.gif


# ---------------------------------------------------------------------------
# Main Widget
# ---------------------------------------------------------------------------
class DesktopPet(QLabel):
    def __init__(self):
        super().__init__()

        self.drag_pos: QPoint | None = None
        self.last_walk_dir: str = "right"  # tracks direction for idle selection
        self.is_dragging = False
        self.velocity_y  = 0
        self.state       = PetState.FALLING

        # Pause / idle timers
        self.pause_trigger_timer = QTimer()   # fires to START a pause while walking
        self.pause_trigger_timer.setSingleShot(True)
        self.pause_trigger_timer.timeout.connect(self._start_pause)

        self.pause_end_timer = QTimer()       # fires to END the pause
        self.pause_end_timer.setSingleShot(True)
        self.pause_end_timer.timeout.connect(self._end_pause)

        self.stumble_timer = QTimer()         # fires to trigger a random stumble/fall
        self.stumble_timer.setSingleShot(True)
        self.stumble_timer.timeout.connect(self._start_stumble)

        self.setup_window()
        self.setup_animation()
        self.setup_physics()
        self.setup_pause()
        self.setup_stumble()
        self.show()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def setup_window(self):
        """設定視窗：無邊框、透明、永遠在最上層"""
        self.setWindowFlags(
            # Qt.WindowType.FramelessWindowHint  |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
            
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Tell Qt this widget paints its own background — required for
        # transparent GIF frames to be cleared between each frame
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.resize(PET_SIZE, PET_SIZE)
        self.move(PET_START_X, PET_START_Y)

    def setup_animation(self):
        """預載所有 GIF (QMovie) 與靜態圖 (QPixmap)"""
        self.movies: dict[str, QMovie] = {}
        for name, path in ANIMATION_MAP.items():
            movie = QMovie(path)
            if movie.isValid():
                # walking GIFs get their own independent instance
                # so left/right never share playback state
                if name in ("walk_to_left", "walk_to_right"):
                    movie.setCacheMode(QMovie.CacheMode.CacheAll)
                self.movies[name] = movie

        self.pixmaps: dict[str, QPixmap] = {}
        for name, path in STATIC_MAP.items():
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.pixmaps[name] = pixmap

        if not self.movies and not self.pixmaps:
            raise FileNotFoundError(
                "No valid animation files found. "
                f"Expected: {list(ANIMATION_MAP.values()) + list(STATIC_MAP.values())}"
            )

        self._play_animation(FALLBACK_ANIMATION)

    def paintEvent(self, event):
        """每幀繪製前先清除背景，避免透明 GIF 殘影"""
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.end()
        super().paintEvent(event)

    def setup_physics(self):
        """啟動物理計時器"""
        self.physics_timer = QTimer()
        self.physics_timer.timeout.connect(self.update_physics)
        self.physics_timer.start(PHYSICS_INTERVAL_MS)

    def setup_pause(self):
        """排程第一次隨機暫停"""
        self._schedule_next_pause()

    def _schedule_next_pause(self):
        """在 PAUSE_INTERVAL_MIN ~ MAX ms 後觸發一次暫停"""
        interval = random.randint(PAUSE_INTERVAL_MIN, PAUSE_INTERVAL_MAX)
        self.pause_trigger_timer.start(interval)

    def _start_pause(self):
        """開始暫停：切換到 PAUSED 狀態，播 idle.gif"""
        # 只在地面行走時暫停
        if self.state not in (PetState.WALK_LEFT, PetState.WALK_RIGHT):
            self._schedule_next_pause()   # not walking yet, try again later
            return
        self.set_state(PetState.PAUSED)
        duration = random.randint(IDLE_DURATION_MIN, IDLE_DURATION_MAX)
        self.pause_end_timer.start(duration)

    def _end_pause(self):
        """暫停結束：恢復行走並排程下一次暫停"""
        if self.state != PetState.PAUSED:
            return
        self.state = PetState.PAUSED   # ensure set_state won't skip
        self.set_state(PetState.WALK_RIGHT)
        self._schedule_next_pause()

    def setup_stumble(self):
        """排程第一次隨機絆倒"""
        self._schedule_next_stumble()

    def _schedule_next_stumble(self):
        """在 STUMBLE_INTERVAL_MIN ~ MAX ms 後觸發一次絆倒"""
        interval = random.randint(STUMBLE_INTERVAL_MIN, STUMBLE_INTERVAL_MAX)
        self.stumble_timer.start(interval)

    def _start_stumble(self):
        """隨機絆倒：只在地面行走時觸發，直接播 fall 動畫一次"""
        if self.state not in (PetState.WALK_LEFT, PetState.WALK_RIGHT):
            self._schedule_next_stumble()   # not walking, try again later
            return
        # Go directly to LANDING (pet is already on the ground)
        # set_state(LANDING) plays the directional fall GIF once,
        # then _on_landing_finished resumes walking
        self.set_state(PetState.LANDING)
        # reschedule happens inside _on_landing_finished after walk resumes

    # ------------------------------------------------------------------
    # State Machine
    # ------------------------------------------------------------------
    def set_state(self, new_state: PetState):
        """切換狀態、同步動畫，並為一次性動畫連接 finished 信號"""
        if self.state == new_state:
            return
        self.state = new_state

        if new_state == PetState.WALK_LEFT:
            self.last_walk_dir = "left"
        elif new_state == PetState.WALK_RIGHT:
            self.last_walk_dir = "right"

        anim_map = {
            PetState.IDLE:       ("anim",   "idle"),
            PetState.WALK_LEFT:  ("anim",   "walk_to_left"),
            PetState.WALK_RIGHT: ("anim",   "walk_to_right"),
            PetState.FALLING:    ("anim",   "falling"),
            PetState.DRAGGED:    ("anim",   "dragged"),
            PetState.DROPPED:    ("anim",   "dropped"),
            PetState.LANDING:    ("once_dir", f"fall_{self.last_walk_dir}"),  # directional fall, once
            PetState.DYING:      ("once",   "die"),       # die.gif plays once
            PetState.PAUSED:     ("idle_dir", f"idle_{self.last_walk_dir}"),
        }

        kind, name = anim_map.get(new_state, ("anim", FALLBACK_ANIMATION))

        if kind == "static":
            self._show_static(name)
        elif kind == "once":
            self._play_once(name)
        elif kind == "once_dir":
            # directional one-shot: fall back to generic "falling" if file missing
            self._play_once(name, fallback="falling")
        elif kind == "idle_dir":
            # fall back to generic "idle" if directional idle GIF is missing
            self._play_animation(name, fallback="idle")
        else:
            self._play_animation(name)

    # ------------------------------------------------------------------
    # Playback helpers
    # ------------------------------------------------------------------
    def _stop_current_movie(self):
        """停止目前播放中的 QMovie"""
        current = self.movie()
        if current is not None:
            current.stop()
            # 安全斷開所有 finished 連接，避免舊回呼殘留
            try:
                current.finished.disconnect()
            except (RuntimeError, TypeError):
                pass

    def _play_animation(self, name: str, fallback: str = FALLBACK_ANIMATION):
        """循環播放 GIF；若不存在則依 fallback 順序嘗試"""
        movie = self.movies.get(name) or self.movies.get(fallback)
        if movie is None:
            return
        self._stop_current_movie()
        movie.stop()
        movie.jumpToFrame(0)
        self.setMovie(movie)
        movie.frameChanged.connect(lambda _: self.repaint())
        movie.start()

    def _play_once(self, name: str, fallback: str | None = None):
        """播放 GIF 一次，結束後依當前 state 觸發回呼"""
        movie = self.movies.get(name)
        if movie is None and fallback:
            movie = self.movies.get(fallback)
        if movie is None:
            # 沒有對應動畫時直接跳到下一步
            if self.state == PetState.LANDING:
                self._on_landing_finished()
            elif self.state == PetState.DYING:
                QApplication.quit()
            return

        self._stop_current_movie()

        # 先清除該 movie 上所有舊的 finished 連接，防止重複觸發
        try:
            movie.finished.disconnect()
        except (RuntimeError, TypeError):
            pass

        movie.stop()
        movie.jumpToFrame(0)

        # 依 state 連接一次性回呼
        if self.state == PetState.LANDING:
            movie.finished.connect(self._on_landing_finished)
        elif self.state == PetState.DYING:
            movie.finished.connect(QApplication.quit)

        self.setMovie(movie)
        movie.frameChanged.connect(lambda _: self.repaint())
        movie.start()

    def _show_static(self, name: str):
        """顯示靜態圖片；若不存在則退回 fallback GIF"""
        pixmap = self.pixmaps.get(name)
        if pixmap is None:
            self._play_animation(FALLBACK_ANIMATION)
            return
        self._stop_current_movie()
        self.setMovie(None)
        self.setPixmap(
            pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ------------------------------------------------------------------
    # One-shot callbacks
    # ------------------------------------------------------------------
    def _on_landing_finished(self):
        """fall.gif 播完 → 繼續往同方向行走"""
        # 斷開所有可能的 fall movie 信號
        for key in ("falling", "fall_left", "fall_right"):
            movie = self.movies.get(key)
            if movie:
                try:
                    movie.finished.disconnect(self._on_landing_finished)
                except (RuntimeError, TypeError):
                    pass
        # 落地後繼續往同方向走
        resume_state = (
            PetState.WALK_LEFT if self.last_walk_dir == "left" else PetState.WALK_RIGHT
        )
        self.state = PetState.LANDING   # 強制重設讓 set_state 不略過
        self.set_state(resume_state)
        self._schedule_next_stumble()   # reschedule after every landing

    # ------------------------------------------------------------------
    # Physics + Walking
    # ------------------------------------------------------------------
    def update_physics(self):
        """每幀：重力 → 落地偵測 → 左右行走 → 邊界反彈"""
        # 這幾個狀態不受物理影響
        if self.is_dragging or self.state in (PetState.DYING, PetState.LANDING, PetState.PAUSED):
            return

        screen     = QApplication.primaryScreen().geometry()
        floor      = screen.height() - self.height() - FLOOR_MARGIN
        left_edge  = -SPRITE_MARGIN                        # let transparent left padding go off-screen
        right_edge = screen.width() - self.width() + SPRITE_MARGIN  # same for right
        current_x  = self.x()
        current_y  = self.y()

        # ── 重力 ──────────────────────────────────────────────────────
        if current_y < floor:
            self.velocity_y = min(self.velocity_y + GRAVITY, MAX_FALL_SPEED)
            self.move(current_x, min(current_y + self.velocity_y, floor))
            # 空中：DROPPED 保持 drop.png；其他顯示 fall GIF
            if self.state != PetState.DROPPED:
                self.set_state(PetState.FALLING)
            return

        # ── 落地 ──────────────────────────────────────────────────────
        self.velocity_y = 0
        self.move(current_x, floor)

        # 從空中狀態落地 → 播 fall.gif 一次（LANDING）
        if self.state in (PetState.FALLING, PetState.DROPPED):
            self.set_state(PetState.LANDING)
            return

        # ── 地面行走 ──────────────────────────────────────────────────
        if self.state == PetState.WALK_LEFT:
            new_x = current_x - WALK_SPEED
            if new_x <= left_edge:
                new_x = left_edge
                self.set_state(PetState.WALK_RIGHT)
            self.move(new_x, floor)

        elif self.state == PetState.WALK_RIGHT:
            new_x = current_x + WALK_SPEED
            if new_x >= right_edge:
                new_x = right_edge
                self.set_state(PetState.WALK_LEFT)
            self.move(new_x, floor)

    # ------------------------------------------------------------------
    # Mouse Events
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        """按下滑鼠：顯示 drag.png"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.velocity_y  = 0
            self.drag_pos    = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            self.set_state(PetState.DRAGGED)

    def mouseMoveEvent(self, event):
        """拖曳中：跟隨滑鼠"""
        if self.drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        """放開滑鼠：顯示 drop.png，等重力帶到地面"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.drag_pos    = None
            self.set_state(PetState.DROPPED)

    # ------------------------------------------------------------------
    # Context Menu
    # ------------------------------------------------------------------
    def contextMenuEvent(self, event):
        """右鍵選單：開啟時暫停並播 idle，關閉後恢復行走"""
        self.physics_timer.stop()
        self.pause_trigger_timer.stop()
        self.pause_end_timer.stop()
        self.stumble_timer.stop()
        self.set_state(PetState.IDLE)

        menu = QMenu(self)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._start_quit)
        menu.addAction(quit_action)

        # aboutToHide fires whether user picks an item or clicks away
        menu.aboutToHide.connect(self._on_menu_close)
        menu.exec(event.globalPos())

    def _on_menu_close(self):
        """選單關閉後恢復物理（Quit 路徑會先 stop timer，不會走到這裡）"""
        if self.state == PetState.DYING:
            return  # Quit was selected — don't restart physics
        self.state = PetState.IDLE  # force set_state to not skip
        self.set_state(PetState.WALK_RIGHT)
        self.physics_timer.start(PHYSICS_INTERVAL_MS)
        self._schedule_next_pause()
        self._schedule_next_stumble()

    def _start_quit(self):
        """停止物理，播 die.gif 一次後關閉"""
        self.physics_timer.stop()
        self.pause_trigger_timer.stop()
        self.pause_end_timer.stop()
        self.stumble_timer.stop()
        self.is_dragging = False
        # Directly call _play_once instead of going through set_state,
        # so DYING state is set AND movie starts atomically before
        # aboutToHide fires _on_menu_close on the next event loop tick
        self.state = PetState.DYING
        self._play_once("die")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    sys.exit(app.exec())