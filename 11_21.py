"""
공 플랫포머 + 테트로미노 사전 설치 데모 (pygame / pygame-ce)

[배치 단계]  A/D 이동 · W 회전 · Space 낙하(설치) · Enter 배치 종료(출발)
[플레이 단계] A/D 이동 · Space 점프(더블 점프) · 벽타기: 초록 블록에 붙어 A/D 유지 + Space 상승 / Ctrl 하강
R: 재시작 · Esc: 종료
"""
#// [AI: Claud] 시작
import random
import sys

import pygame

# ------------------------------------------------------------------ 설정
T = 30                       # 타일(블록) 크기
COLS, ROWS = 40, 20
HUD_H = 90
W, H = COLS * T, ROWS * T + HUD_H
FPS = 60

GROUND_TOP = 15              # 땅이 시작되는 행
PITS = [(10, 13), (19, 23), (29, 32)]   # 구덩이 열 범위(양끝 포함) - 바닥에 가시
BUILD_MIN_COL = 4            # 설치 가능한 열 범위 (왼쪽 시작 지점 / 오른쪽 골 지역 제외)
GOAL_COL = 36
BUILD_MAX_COL = GOAL_COL - 1
PIECE_COUNT = 5              # 시작 시 주어지는 구조물 개수

BALL = 26                    # 공 판정 크기
SPEED = 240
GRAVITY = 2000
JUMP_V = -600
MAX_FALL = 800
CLIMB_SPEED = 150
MANTLE_V = -300              # 벽 꼭대기를 넘어갈 때의 작은 점프
MAX_HP = 3
INVULN_TIME = 1.2

SPAWN_INTERVAL = 5.0         # 하늘에서 구조물이 떨어지는 주기(초)
FALL_SPEED = 220
WARN_TIME = 1.2              # 낙하 직전 경고 표시 시간

BG = (24, 28, 44)
CLIMB_COLOR = (70, 190, 110)     # 벽타기 가능
PLAIN_COLOR = (120, 130, 165)    # 벽타기 불가
GROUND_COLOR = (96, 72, 52)
GROUND = ("ground", GROUND_COLOR, False)
SPIKE = ("spike", (225, 60, 60), False)

SHAPES = {
    "I": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
    "J": [(0, 0), (0, 1), (1, 1), (2, 1)],
    "L": [(2, 0), (0, 1), (1, 1), (2, 1)],
}


# ------------------------------------------------------------------ 유틸
def rotate_cells(cells):
    rot = [(-y, x) for x, y in cells]
    mx = min(x for x, _ in rot)
    my = min(y for _, y in rot)
    return [(x - mx, y - my) for x, y in rot]


def load_font(size):
    return pygame.font.SysFont("malgungothic,nanumgothic,applegothic,notosanscjkkr,arial", size)


def cell_at(grid, r, c):
    if c < 0 or c >= COLS or r >= ROWS:
        return GROUND            # 맵 좌우/아래 바깥은 벽
    if r < 0:
        return None              # 위쪽은 열린 하늘
    return grid[r][c]


def is_solid(cell):
    return cell is not None and cell[0] != "spike"


def span(x, y, w, h):
    return int(x // T), int((x + w - 0.001) // T), int(y // T), int((y + h - 0.001) // T)


def make_grid():
    grid = [[None] * COLS for _ in range(ROWS)]
    for r in range(GROUND_TOP, ROWS):
        for c in range(COLS):
            grid[r][c] = GROUND
    for a, b in PITS:
        for c in range(a, b + 1):
            for r in range(GROUND_TOP, ROWS):
                grid[r][c] = None
            grid[ROWS - 1][c] = SPIKE      # 구덩이 바닥의 즉사 함정
    return grid


def draw_cell(surf, x, y, color, climb, size=T):
    rect = pygame.Rect(int(x), int(y), size, size)
    pygame.draw.rect(surf, color, rect)
    dark = tuple(max(0, v - 70) for v in color)
    pygame.draw.rect(surf, dark, rect, 2)
    if climb:   # 벽타기 가능 표시: 좌우 가장자리의 그립 선
        n = max(4, size // 6)
        for i in range(1, 4):
            yy = rect.y + i * size // 4
            pygame.draw.line(surf, (225, 255, 225), (rect.x + 2, yy), (rect.x + 2 + n, yy), 2)
            pygame.draw.line(surf, (225, 255, 225), (rect.right - 3 - n, yy), (rect.right - 3, yy), 2)


# ------------------------------------------------------------------ 구조물
class Piece:
    def __init__(self):
        self.name = random.choice(list(SHAPES))
        self.cells = SHAPES[self.name]
        for _ in range(random.randint(0, 3)):
            self.rotate()
        self.climb = random.random() < 0.5

    def rotate(self):
        self.cells = rotate_cells(self.cells)

    @property
    def width(self):
        return max(x for x, _ in self.cells) + 1

    @property
    def height(self):
        return max(y for _, y in self.cells) + 1

    @property
    def color(self):
        return CLIMB_COLOR if self.climb else PLAIN_COLOR


class Falling:
    def __init__(self, piece, col):
        self.piece = piece
        self.col = col
        self.y = -piece.height * T      # 화면 위에서 시작


# ------------------------------------------------------------------ 공
class Ball:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = 1 * T + (T - BALL) / 2
        self.y = GROUND_TOP * T - BALL
        self.vx = self.vy = 0.0
        self.on_ground = False
        self.jumps_left = 2
        self.cling_dir = 0
        self.hp = MAX_HP
        self.invuln = 0.0
        self.dead = False

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), BALL, BALL)

    # --- 충돌
    def solid_cells(self, grid):
        c0, c1, r0, r1 = span(self.x, self.y, BALL, BALL)
        return [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)
                if is_solid(cell_at(grid, r, c))]

    def move_x(self, grid, dx):
        self.x += dx
        hits = self.solid_cells(grid)
        if hits:
            if dx > 0:
                self.x = min(c for _, c in hits) * T - BALL
            elif dx < 0:
                self.x = (max(c for _, c in hits) + 1) * T
            self.vx = 0

    def move_y(self, grid, dy):
        self.y += dy
        hits = self.solid_cells(grid)
        if hits:
            if dy > 0:
                self.y = min(r for r, _ in hits) * T - BALL
                self.on_ground = True
            elif dy < 0:
                self.y = (max(r for r, _ in hits) + 1) * T
            self.vy = 0

    def wall_climbable(self, grid, d):
        """d 방향(-1 왼쪽 / +1 오른쪽)에 밀착한 벽타기 가능 블록이 있는가"""
        px = self.x - 1 if d < 0 else self.x + BALL + 1
        c = int(px // T)
        r0 = int(self.y // T)
        r1 = int((self.y + BALL - 0.001) // T)
        for r in range(r0, r1 + 1):
            cell = cell_at(grid, r, c)
            if cell and cell[0] == "block" and cell[2]:
                return True
        return False

    def unstuck(self, grid):
        n = 0
        while self.solid_cells(grid) and n < 300:
            self.y -= 2
            n += 1
        self.vy = 0

    def hurt(self):
        if self.invuln > 0:
            return
        self.hp -= 1
        self.invuln = INVULN_TIME
        if self.hp <= 0:
            self.dead = True

    # --- 입력/갱신
    @staticmethod
    def _axis(keys):
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        return int(bool(right)) - int(bool(left))

    def jump(self, grid, keys):
        ax = self._axis(keys)
        if ax and self.wall_climbable(grid, ax):
            return                      # 벽에 붙는 입력이면 점프 대신 벽타기
        if self.jumps_left > 0:
            self.vy = JUMP_V
            self.jumps_left -= 1
            self.on_ground = False

    def update(self, dt, keys, grid):
        ax = self._axis(keys)
        space = keys[pygame.K_SPACE]
        ctrl = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
        self.invuln = max(0.0, self.invuln - dt)

        prev_cling = self.cling_dir
        cling = 0
        if ax != 0 and self.wall_climbable(grid, ax) and (not self.on_ground or space):
            cling = ax

        if cling:
            self.cling_dir = cling
            self.vx = 0
            if space and not ctrl:
                self.vy = -CLIMB_SPEED
            elif ctrl and not space:
                self.vy = CLIMB_SPEED
            else:
                self.vy = 0
            self.jumps_left = 1
        else:
            self.cling_dir = 0
            self.vx = ax * SPEED
            self.vy = min(self.vy + GRAVITY * dt, MAX_FALL)
            if prev_cling and space and ax == prev_cling:
                self.vy = MANTLE_V      # 벽 꼭대기를 넘어 올라서기

        was_ground = self.on_ground
        self.on_ground = False
        self.move_x(grid, self.vx * dt)
        self.move_y(grid, self.vy * dt)
        if was_ground and not self.on_ground:
            self.jumps_left = min(self.jumps_left, 1)
        if self.on_ground:
            self.jumps_left = 2

        # 가시: 닿으면 즉사
        c0, c1, r0, r1 = span(self.x + 4, self.y + 4, BALL - 8, BALL - 8)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cell = cell_at(grid, r, c)
                if cell and cell[0] == "spike":
                    self.dead = True

    def draw(self, surf):
        if self.invuln > 0 and int(self.invuln * 10) % 2 == 0:
            return
        cx, cy = int(self.x + BALL / 2), int(self.y + BALL / 2)
        pygame.draw.circle(surf, (255, 170, 40), (cx, cy), BALL // 2)
        pygame.draw.circle(surf, (255, 235, 160), (cx - 4, cy - 4), 4)
        pygame.draw.circle(surf, (150, 80, 10), (cx, cy), BALL // 2, 2)
        if self.cling_dir:
            xx = cx + self.cling_dir * (BALL // 2 + 1)
            pygame.draw.line(surf, (255, 255, 255), (xx, cy - 8), (xx, cy + 8), 3)


# ------------------------------------------------------------------ 게임
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("공 플랫포머 + 테트로미노 데모")
        self.clock = pygame.time.Clock()
        self.font = load_font(20)
        self.small = load_font(16)
        self.big = load_font(56)

        self.ghost_tile = pygame.Surface((T, T), pygame.SRCALPHA)
        self.ghost_tile.fill((255, 255, 255, 70))
        self.nobuild = pygame.Surface((T, GROUND_TOP * T), pygame.SRCALPHA)
        self.nobuild.fill((0, 0, 0, 90))
        self.goal_zone = pygame.Surface(((COLS - GOAL_COL) * T, GROUND_TOP * T), pygame.SRCALPHA)
        self.goal_zone.fill((255, 220, 80, 35))
        self.warn_tile = pygame.Surface((T, 44), pygame.SRCALPHA)
        self.warn_tile.fill((255, 60, 60, 120))
        self.dim = pygame.Surface((W, ROWS * T), pygame.SRCALPHA)
        self.dim.fill((0, 0, 0, 150))
        self.reset()

    def reset(self):
        self.grid = make_grid()
        self.ball = Ball()
        self.phase = "build"          # build / play / dead / win
        self.queue = [Piece() for _ in range(PIECE_COUNT)]
        self.cur = self.queue.pop(0)
        self.cur_col = BUILD_MIN_COL + 4
        self.clamp_col()
        self.hold_dir = 0
        self.hold_t = 0.0
        self.falling = []
        self.pending = None
        self.spawn_timer = 0.0
        self.time = 0.0

    # --- 배치 단계
    def clamp_col(self):
        hi = BUILD_MAX_COL - self.cur.width + 1
        self.cur_col = max(BUILD_MIN_COL, min(hi, self.cur_col))

    def piece_fits(self, piece, col, row):
        for dx, dy in piece.cells:
            c, r = col + dx, row + dy
            if not (BUILD_MIN_COL <= c <= BUILD_MAX_COL) or r >= ROWS:
                return False
            if r >= 0 and self.grid[r][c] is not None:
                return False
        return True

    def drop_row(self, piece, col):
        if not self.piece_fits(piece, col, 0):
            return None
        row = 0
        while self.piece_fits(piece, col, row + 1):
            row += 1
        return row

    def drop_current(self):
        row = self.drop_row(self.cur, self.cur_col)
        if row is None:
            return
        for dx, dy in self.cur.cells:
            self.grid[row + dy][self.cur_col + dx] = ("block", self.cur.color, self.cur.climb)
        if self.queue:
            self.cur = self.queue.pop(0)
            self.clamp_col()
        else:
            self.cur = None
            self.start_play()

    def start_play(self):
        self.cur = None
        self.queue = []
        self.phase = "play"
        self.spawn_timer = 3.0
        self.make_pending()

    def build_input(self, dt):
        keys = pygame.key.get_pressed()
        d = int(bool(keys[pygame.K_d] or keys[pygame.K_RIGHT])) - int(bool(keys[pygame.K_a] or keys[pygame.K_LEFT]))
        if d == 0:
            self.hold_dir = 0
            return
        if d != self.hold_dir:
            self.hold_dir = d
            self.cur_col += d
            self.clamp_col()
            self.hold_t = 0.25
        else:
            self.hold_t -= dt
            if self.hold_t <= 0:
                self.cur_col += d
                self.clamp_col()
                self.hold_t = 0.05

    # --- 플레이 단계
    def make_pending(self):
        p = Piece()
        col = random.randint(BUILD_MIN_COL, BUILD_MAX_COL - p.width + 1)
        self.pending = (p, col)

    def step_falling(self, fp, dt):
        """낙하 갱신. 착지하면 격자에 고정하고 True 반환"""
        new_y = fp.y + FALL_SPEED * dt
        land_y = None
        for dx, dy in fp.piece.cells:
            c = fp.col + dx
            r = int((new_y + (dy + 1) * T) // T)
            if 0 <= r < ROWS and self.grid[r][c] is not None:
                y_c = r * T - (dy + 1) * T
                land_y = y_c if land_y is None else min(land_y, y_c)
        if land_y is None:
            fp.y = new_y
            return False
        fp.y = land_y
        for dx, dy in fp.piece.cells:
            r = int(round((land_y + dy * T) / T))
            c = fp.col + dx
            if 0 <= r < ROWS:
                self.grid[r][c] = ("block", fp.piece.color, fp.piece.climb)
        return True

    def update_play(self, dt):
        self.time += dt
        keys = pygame.key.get_pressed()
        self.ball.update(dt, keys, self.grid)

        self.spawn_timer -= dt
        if self.spawn_timer <= 0 and self.pending:
            p, col = self.pending
            self.falling.append(Falling(p, col))
            self.make_pending()
            self.spawn_timer = SPAWN_INTERVAL

        hit_box = self.ball.rect.inflate(-4, -4)
        for fp in self.falling[:]:
            # 낙하 중인 구조물에 맞으면 피해
            for dx, dy in fp.piece.cells:
                cell_rect = pygame.Rect((fp.col + dx) * T, int(fp.y) + dy * T, T, T)
                if cell_rect.colliderect(hit_box):
                    self.ball.hurt()
            if self.step_falling(fp, dt):
                self.falling.remove(fp)
                if self.ball.solid_cells(self.grid):     # 착지한 블록에 공이 끼면 위로 밀어냄
                    self.ball.hurt()
                    self.ball.unstuck(self.grid)

        if self.ball.dead:
            self.phase = "dead"
        elif self.ball.x + BALL / 2 >= GOAL_COL * T:
            self.phase = "win"

    # --- 그리기
    def text(self, s, font, pos, color=(255, 255, 255)):
        self.screen.blit(font.render(s, True, (0, 0, 0)), (pos[0] + 1, pos[1] + 1))
        self.screen.blit(font.render(s, True, color), pos)

    def draw_world(self):
        s = self.screen
        s.fill(BG)
        s.blit(self.goal_zone, (GOAL_COL * T, 0))
        for r in range(ROWS):
            for c in range(COLS):
                cell = self.grid[r][c]
                if not cell:
                    continue
                x, y = c * T, r * T
                kind = cell[0]
                if kind == "ground":
                    pygame.draw.rect(s, cell[1], (x, y, T, T))
                    pygame.draw.rect(s, (70, 50, 36), (x, y, T, T), 1)
                    if cell_at(self.grid, r - 1, c) is None:
                        pygame.draw.rect(s, (80, 170, 80), (x, y, T, 6))
                elif kind == "spike":
                    pygame.draw.polygon(s, cell[1], [(x + 2, y + T), (x + T // 2, y + 6), (x + T - 2, y + T)])
                else:
                    draw_cell(s, x, y, cell[1], cell[2])
        # 시작 / 골 표시
        self.text("START", self.small, (T, (GROUND_TOP - 3) * T))
        px = (COLS - 2) * T + 12
        pygame.draw.rect(s, (230, 230, 230), (px, (GROUND_TOP - 4) * T, 4, 4 * T))
        pygame.draw.polygon(s, (255, 90, 90), [(px + 4, (GROUND_TOP - 4) * T), (px + 4 + 30, (GROUND_TOP - 4) * T + 12),
                                               (px + 4, (GROUND_TOP - 4) * T + 24)])
        self.text("GOAL", self.small, (px - 12, (GROUND_TOP - 5) * T - 6), (255, 230, 120))

    def draw_pieces(self):
        if self.phase == "build":
            for c in list(range(0, BUILD_MIN_COL)) + list(range(GOAL_COL, COLS)):
                self.screen.blit(self.nobuild, (c * T, 0))
            if self.cur:
                row = self.drop_row(self.cur, self.cur_col)
                if row is not None:
                    for dx, dy in self.cur.cells:
                        x, y = (self.cur_col + dx) * T, (row + dy) * T
                        self.screen.blit(self.ghost_tile, (x, y))
                        pygame.draw.rect(self.screen, (255, 255, 255), (x, y, T, T), 1)
                for dx, dy in self.cur.cells:
                    draw_cell(self.screen, (self.cur_col + dx) * T, dy * T, self.cur.color, self.cur.climb)
        for fp in self.falling:
            for dx, dy in fp.piece.cells:
                draw_cell(self.screen, (fp.col + dx) * T, fp.y + dy * T, fp.piece.color, fp.piece.climb)
        # 다음 낙하 경고
        if self.phase == "play" and self.pending and self.spawn_timer < WARN_TIME:
            if int(self.spawn_timer * 6) % 2 == 0:
                p, col = self.pending
                for cx in sorted({col + dx for dx, _ in p.cells}):
                    self.screen.blit(self.warn_tile, (cx * T, 0))
                    self.text("!", self.font, (cx * T + T // 2 - 3, 8), (255, 255, 255))

    def draw_hud(self):
        y0 = ROWS * T
        pygame.draw.rect(self.screen, (16, 18, 28), (0, y0, W, HUD_H))
        pygame.draw.line(self.screen, (60, 64, 90), (0, y0), (W, y0), 2)
        x, y = 14, y0 + 8
        if self.phase == "build":
            remain = len(self.queue) + (1 if self.cur else 0)
            self.text(f"[배치 단계] 남은 구조물 {remain}개", self.font, (x, y), (255, 220, 120))
            self.text("A/D 좌우 이동 · W 회전 · Space 낙하(설치) · Enter 배치 종료하고 출발", self.small, (x, y + 28))
            self.text("초록 블록 = 벽타기 가능 / 회색 블록 = 벽타기 불가 · 구덩이 바닥의 가시는 즉사 · 오른쪽 깃발이 목표",
                      self.small, (x, y + 52))
            self.text("다음 구조물", self.small, (W - 330, y))
            for i, p in enumerate(self.queue):
                for dx, dy in p.cells:
                    draw_cell(self.screen, W - 330 + i * 64 + dx * 12, y + 26 + dy * 12, p.color, p.climb, 12)
        else:
            self.text("HP", self.font, (x, y))
            for i in range(MAX_HP):
                col = (235, 60, 80) if i < self.ball.hp else (70, 70, 80)
                pygame.draw.circle(self.screen, col, (x + 44 + i * 26, y + 12), 9)
            self.text(f"생존 시간 {self.time:5.1f}초", self.font, (x + 150, y))
            self.text("A/D 이동 · Space 점프(더블 점프) · 벽타기: 초록 블록에 붙어 A/D를 누른 채 Space 상승 / Ctrl 하강",
                      self.small, (x, y + 28))
            self.text("하늘에서 떨어지는 구조물에 맞으면 HP -1 · 가시는 즉사 · R 재시작", self.small, (x, y + 52))

    def draw_banner(self):
        if self.phase not in ("dead", "win"):
            return
        self.screen.blit(self.dim, (0, 0))
        msg = "클리어!" if self.phase == "win" else "게임 오버"
        color = (255, 230, 120) if self.phase == "win" else (255, 110, 110)
        surf = self.big.render(msg, True, color)
        self.screen.blit(surf, surf.get_rect(center=(W // 2, ROWS * T // 2 - 20)))
        sub = self.font.render("R 키로 다시 시작", True, (255, 255, 255))
        self.screen.blit(sub, sub.get_rect(center=(W // 2, ROWS * T // 2 + 36)))

    # --- 메인 루프
    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                    if e.key == pygame.K_r:
                        self.reset()
                        continue
                    if self.phase == "build" and self.cur:
                        if e.key in (pygame.K_w, pygame.K_UP):
                            self.cur.rotate()
                            self.clamp_col()
                        elif e.key == pygame.K_SPACE:
                            self.drop_current()
                        elif e.key == pygame.K_RETURN:
                            self.start_play()
                    elif self.phase == "play" and e.key == pygame.K_SPACE:
                        self.ball.jump(self.grid, pygame.key.get_pressed())

            if self.phase == "build":
                self.build_input(dt)
            elif self.phase == "play":
                self.update_play(dt)

            self.draw_world()
            self.draw_pieces()
            self.ball.draw(self.screen)
            self.draw_banner()
            self.draw_hud()
            pygame.display.flip()


if __name__ == "__main__":
    Game().run()
#// [AI: Claud] 끝