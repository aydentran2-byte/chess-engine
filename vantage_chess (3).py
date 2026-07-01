"""
VANTAGE CHESS  —  Python / Pygame Edition
===========================================
A faithful port of the "Vantage Chess" web app to a desktop Python app
you can run in Visual Studio / VS Code.

Features ported from the original HTML/JS version:
  - Full chess rules: legal move generation, check/checkmate/stalemate
    detection, castling, en passant, pawn promotion (auto-queen).
  - Play vs AI with 4 difficulty levels (Easy / Normal / Medium / Hard),
    using the same material + piece-square-table evaluation and
    minimax + alpha-beta search as the original.
  - Choose to play as White or Black vs the AI.
  - Local 2-Player (hot-seat) mode, replacing the original's online
    room feature (which depended on a web backend / browser storage
    that isn't available outside the browser).
  - Move history panel, captured-piece tray, check highlighting,
    legal-move dots/rings, last-move highlight, resign button.

Requirements
------------
    pip install pygame

Run
---
    python vantage_chess.py
"""

import sys
import random
import copy
import json
import ssl
import queue
import threading
import urllib.request
import urllib.error
import pygame

# =========================================================
#  CHESS ENGINE  (direct port of the JS engine)
# =========================================================

PIECE_GLYPH = {
    'w': {'k': '\u2654', 'q': '\u2655', 'r': '\u2656', 'b': '\u2657', 'n': '\u2658', 'p': '\u2659'},
    'b': {'k': '\u265A', 'q': '\u265B', 'r': '\u265C', 'b': '\u265D', 'n': '\u265E', 'p': '\u265F'},
}
VALUES = {'p': 100, 'n': 320, 'b': 330, 'r': 500, 'q': 900, 'k': 20000}


def initial_board():
    back = ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r']
    board = [[None] * 8 for _ in range(8)]
    for c in range(8):
        board[0][c] = {'type': back[c], 'color': 'b', 'moved': False}
        board[1][c] = {'type': 'p', 'color': 'b', 'moved': False}
        board[6][c] = {'type': 'p', 'color': 'w', 'moved': False}
        board[7][c] = {'type': back[c], 'color': 'w', 'moved': False}
    return board


def clone_board(board):
    return [[(dict(p) if p else None) for p in row] for row in board]


def in_bounds(r, c):
    return 0 <= r < 8 and 0 <= c < 8


def find_king(board, color):
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p and p['type'] == 'k' and p['color'] == color:
                return (r, c)
    return None


def is_square_attacked(board, r, c, by_color):
    # pawns
    for dc in (-1, 1):
        rr, cc = r + (1 if by_color == 'w' else -1), c + dc
        if in_bounds(rr, cc):
            p = board[rr][cc]
            if p and p['color'] == by_color and p['type'] == 'p':
                return True
    # knights
    for dr, dc in [(1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)]:
        rr, cc = r + dr, c + dc
        if in_bounds(rr, cc):
            p = board[rr][cc]
            if p and p['color'] == by_color and p['type'] == 'n':
                return True
    # king
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            rr, cc = r + dr, c + dc
            if in_bounds(rr, cc):
                p = board[rr][cc]
                if p and p['color'] == by_color and p['type'] == 'k':
                    return True
    # rook / queen
    for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        rr, cc = r + dr, c + dc
        while in_bounds(rr, cc):
            p = board[rr][cc]
            if p:
                if p['color'] == by_color and p['type'] in ('r', 'q'):
                    return True
                break
            rr += dr
            cc += dc
    # bishop / queen
    for dr, dc in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
        rr, cc = r + dr, c + dc
        while in_bounds(rr, cc):
            p = board[rr][cc]
            if p:
                if p['color'] == by_color and p['type'] in ('b', 'q'):
                    return True
                break
            rr += dr
            cc += dc
    return False


def is_in_check(board, color):
    k = find_king(board, color)
    if not k:
        return False
    return is_square_attacked(board, k[0], k[1], 'b' if color == 'w' else 'w')


def pseudo_moves(board, r, c, state):
    p = board[r][c]
    if not p:
        return []
    moves = []
    opp = 'b' if p['color'] == 'w' else 'w'

    def add(rr, cc, extra=None):
        if not in_bounds(rr, cc):
            return False
        target = board[rr][cc]
        if target and target['color'] == p['color']:
            return False
        m = {'from': (r, c), 'to': (rr, cc), 'captured': target}
        if extra:
            m.update(extra)
        moves.append(m)
        return target is None

    if p['type'] == 'p':
        direction = -1 if p['color'] == 'w' else 1
        start_row = 6 if p['color'] == 'w' else 1
        promo_row = 0 if p['color'] == 'w' else 7
        if in_bounds(r + direction, c) and not board[r + direction][c]:
            moves.append({'from': (r, c), 'to': (r + direction, c), 'captured': None,
                          'promotion': (r + direction == promo_row)})
            if r == start_row and not board[r + 2 * direction][c]:
                moves.append({'from': (r, c), 'to': (r + 2 * direction, c), 'captured': None,
                              'doubleStep': True})
        for dc in (-1, 1):
            rr, cc = r + direction, c + dc
            if in_bounds(rr, cc):
                target = board[rr][cc]
                if target and target['color'] == opp:
                    moves.append({'from': (r, c), 'to': (rr, cc), 'captured': target,
                                  'promotion': (rr == promo_row)})
                elif state.get('enPassant') and state['enPassant'] == (rr, cc):
                    moves.append({'from': (r, c), 'to': (rr, cc), 'captured': board[r][cc],
                                  'enPassant': True})
    elif p['type'] == 'n':
        for dr, dc in [(1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)]:
            add(r + dr, c + dc)
    elif p['type'] == 'k':
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                add(r + dr, c + dc)
        if not p['moved'] and not is_in_check(board, p['color']):
            row = 7 if p['color'] == 'w' else 0
            krk = board[row][7]
            if (krk and krk['type'] == 'r' and not krk['moved']
                    and not board[row][5] and not board[row][6]
                    and not is_square_attacked(board, row, 5, opp)
                    and not is_square_attacked(board, row, 6, opp)):
                moves.append({'from': (r, c), 'to': (row, 6), 'captured': None, 'castle': 'K'})
            qrk = board[row][0]
            if (qrk and qrk['type'] == 'r' and not qrk['moved']
                    and not board[row][1] and not board[row][2] and not board[row][3]
                    and not is_square_attacked(board, row, 2, opp)
                    and not is_square_attacked(board, row, 3, opp)):
                moves.append({'from': (r, c), 'to': (row, 2), 'captured': None, 'castle': 'Q'})
    else:
        dirs = []
        if p['type'] == 'r':
            dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if p['type'] == 'b':
            dirs = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        if p['type'] == 'q':
            dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        for dr, dc in dirs:
            rr, cc = r + dr, c + dc
            while add(rr, cc):
                rr += dr
                cc += dc
    return moves


def all_pseudo_moves(board, color, state):
    all_moves = []
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p and p['color'] == color:
                all_moves.extend(pseudo_moves(board, r, c, state))
    return all_moves


def apply_move(board, state, move):
    nb = clone_board(board)
    fr, fc = move['from']
    tr, tc = move['to']
    piece = nb[fr][fc]
    new_en_passant = None

    if move.get('enPassant'):
        nb[fr][tc] = None  # captured pawn sits behind target square

    nb[tr][tc] = piece
    nb[fr][fc] = None
    piece['moved'] = True

    if move.get('promotion'):
        piece['type'] = move.get('promoteTo', 'q')

    if move.get('castle') == 'K':
        row = fr
        nb[row][5] = nb[row][7]
        nb[row][7] = None
        nb[row][5]['moved'] = True
    if move.get('castle') == 'Q':
        row = fr
        nb[row][3] = nb[row][0]
        nb[row][0] = None
        nb[row][3]['moved'] = True
    if move.get('doubleStep'):
        new_en_passant = ((fr + tr) // 2, fc)

    new_state = dict(state)
    new_state['enPassant'] = new_en_passant
    return nb, new_state


def legal_moves(board, color, state):
    pseudo = all_pseudo_moves(board, color, state)
    legal = []
    for m in pseudo:
        nb, _ = apply_move(board, state, m)
        if not is_in_check(nb, color):
            legal.append(m)
    return legal


def game_status(board, state, color):
    moves = legal_moves(board, color, state)
    check = is_in_check(board, color)
    if not moves:
        return 'checkmate' if check else 'stalemate'
    return 'check' if check else 'normal'


# ---------- Evaluation & AI ----------
PST_PAWN = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [50, 50, 50, 50, 50, 50, 50, 50],
    [10, 10, 20, 30, 30, 20, 10, 10],
    [5, 5, 10, 25, 25, 10, 5, 5],
    [0, 0, 0, 20, 20, 0, 0, 0],
    [5, -5, -10, 0, 0, -10, -5, 5],
    [5, 10, 10, -20, -20, 10, 10, 5],
    [0, 0, 0, 0, 0, 0, 0, 0],
]
PST_KNIGHT = [
    [-50, -40, -30, -30, -30, -30, -40, -50],
    [-40, -20, 0, 0, 0, 0, -20, -40],
    [-30, 0, 10, 15, 15, 10, 0, -30],
    [-30, 5, 15, 20, 20, 15, 5, -30],
    [-30, 0, 15, 20, 20, 15, 0, -30],
    [-30, 5, 10, 15, 15, 10, 5, -30],
    [-40, -20, 0, 5, 5, 0, -20, -40],
    [-50, -40, -30, -30, -30, -30, -40, -50],
]


def pst_value(ptype, r, c, color):
    rr = r if color == 'w' else 7 - r
    if ptype == 'p':
        return PST_PAWN[rr][c]
    if ptype == 'n':
        return PST_KNIGHT[rr][c]
    return 0


def evaluate(board):
    score = 0
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if not p:
                continue
            v = VALUES[p['type']] + pst_value(p['type'], r, c, p['color'])
            score += v if p['color'] == 'w' else -v
    return score


def order_moves(moves):
    def key(m):
        return VALUES[m['captured']['type']] if m.get('captured') else 0
    return sorted(moves, key=key, reverse=True)


def minimax(board, state, depth, alpha, beta, maximizing):
    color = 'w' if maximizing else 'b'
    moves = legal_moves(board, color, state)
    if depth == 0 or not moves:
        if not moves:
            if is_in_check(board, color):
                return (-99999 + depth) if maximizing else (99999 - depth)
            return 0
        return evaluate(board)
    ordered = order_moves(moves)
    if maximizing:
        best = -float('inf')
        for m in ordered:
            nb, ns = apply_move(board, state, m)
            val = minimax(nb, ns, depth - 1, alpha, beta, False)
            best = max(best, val)
            alpha = max(alpha, val)
            if beta <= alpha:
                break
        return best
    else:
        best = float('inf')
        for m in ordered:
            nb, ns = apply_move(board, state, m)
            val = minimax(nb, ns, depth - 1, alpha, beta, True)
            best = min(best, val)
            beta = min(beta, val)
            if beta <= alpha:
                break
        return best


def pick_ai_move(board, state, color, difficulty):
    moves = legal_moves(board, color, state)
    if not moves:
        return None
    maximizing = (color == 'w')
    ordered = order_moves(moves)

    if difficulty == 1:
        scored = []
        for m in ordered:
            nb, _ = apply_move(board, state, m)
            v = evaluate(nb) * (1 if maximizing else -1)
            scored.append((v, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        pool = scored[:min(4, len(scored))]
        return random.choice(pool)[1]

    depth = 2 if difficulty == 2 else (3 if difficulty == 3 else 4)
    best_move = ordered[0]
    best_val = -float('inf') if maximizing else float('inf')
    for m in ordered:
        nb, ns = apply_move(board, state, m)
        val = minimax(nb, ns, depth - 1, -float('inf'), float('inf'), not maximizing)
        if (maximizing and val > best_val) or (not maximizing and val < best_val):
            best_val = val
            best_move = m
    return best_move


def move_notation(move, piece):
    files = 'abcdefgh'
    tr, tc = move['to']
    dest = files[tc] + str(8 - tr)
    if move.get('castle') == 'K':
        return 'O-O'
    if move.get('castle') == 'Q':
        return 'O-O-O'
    piece_letter = '' if piece['type'] == 'p' else piece['type'].upper()
    capture = 'x' if move.get('captured') else ''
    from_part = ''
    if piece['type'] == 'p' and move.get('captured'):
        from_part = files[move['from'][1]]
    promo = '=Q' if move.get('promotion') else ''
    return piece_letter + from_part + capture + dest + promo


# =========================================================
#  ONLINE PLAY  (free, no-signup relay via jsonblob.com)
# =========================================================
#
# One player "hosts" a game: this creates a small JSON blob on jsonblob.com
# and returns its id, which is the shareable "game code". The other player
# "joins" by typing/pasting that same code. Both sides simply poll the blob
# over plain HTTPS every ~1.5s and push their own moves to it — there's no
# server to set up and nothing to install.

JSONBLOB_BASE = "https://jsonblob.com/api/jsonBlob"


def _urlopen(req, timeout=6):
    """Open a request, falling back to an unverified SSL context if the
    server's certificate can't be validated, so a single flaky relay host
    doesn't hard-fail online play."""
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        raise


def relay_create(initial_obj):
    """Creates a new shared JSON blob and returns its id (the 'game code')."""
    data = json.dumps(initial_obj).encode("utf-8")
    req = urllib.request.Request(JSONBLOB_BASE, data=data, method="POST",
                                  headers={"Content-Type": "application/json",
                                           "Accept": "application/json",
                                           "User-Agent": "VantageChess/1.0"})
    with _urlopen(req) as resp:
        location = resp.headers.get("Location") or resp.geturl()
    if not location:
        raise RuntimeError("relay did not return a game id")
    return location.rstrip("/").split("/")[-1]


def relay_set(blob_id, obj):
    url = f"{JSONBLOB_BASE}/{blob_id}"
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT",
                                  headers={"Content-Type": "application/json",
                                           "Accept": "application/json",
                                           "User-Agent": "VantageChess/1.0"})
    with _urlopen(req):
        pass


def relay_get(blob_id):
    url = f"{JSONBLOB_BASE}/{blob_id}"
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                 "User-Agent": "VantageChess/1.0"})
    try:
        with _urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def serialize_board(board):
    rows = []
    for row in board:
        cells = []
        for p in row:
            cells.append('--' if not p else p['color'] + p['type'] + ('1' if p['moved'] else '0'))
        rows.append(','.join(cells))
    return '|'.join(rows)


def deserialize_board(s):
    board = []
    for row_str in s.split('|'):
        row = []
        for cell in row_str.split(','):
            if cell == '--':
                row.append(None)
            else:
                row.append({'color': cell[0], 'type': cell[1], 'moved': cell[2] == '1'})
        board.append(row)
    return board


def serialize_state_for_relay(G):
    return {
        'boardFEN': serialize_board(G['board']),
        'turn': G['turn'],
        'enPassant': list(G['enPassant']) if G['enPassant'] else None,
        'history': G['history'],
        'captured': G['captured'],
        'status': G['status'],
        'version': G['version'],
        'whiteJoined': True,
        'blackJoined': True,
        'resigned': G.get('resigned'),
    }


def load_state_from_relay(G, r):
    G['board'] = deserialize_board(r['boardFEN'])
    G['turn'] = r['turn']
    ep = r.get('enPassant')
    G['enPassant'] = tuple(ep) if ep else None
    G['history'] = r['history']
    G['captured'] = r['captured']
    G['status'] = r['status']
    G['version'] = r['version']
    G['resigned'] = r.get('resigned')
    G['gameOver'] = (r['status'] in ('checkmate', 'stalemate')) or bool(r.get('resigned'))
    G['selected'] = None
    G['legalForSelected'] = []
    G['lastMove'] = None


# =========================================================
#  CLIPBOARD  (copy/paste the room code)
# =========================================================
# Uses tkinter's clipboard (part of the Python standard library on Windows/
# macOS, and on most Linux distros with Tk installed) so copy/paste works
# without any extra pip packages. Pygame itself has no reliable built-in
# clipboard support across platforms.

def clipboard_copy(text):
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()  # flush the clipboard write before destroying the window
        r.destroy()
        return True
    except Exception:
        return False


def clipboard_paste():
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        return text
    except Exception:
        return ''


# =========================================================
#  PYGAME UI
# =========================================================

SQ = 78
BOARD_PX = SQ * 8
SIDEBAR_W = 320
PAD = 24
WIN_W = BOARD_PX + SIDEBAR_W + PAD * 3
WIN_H = BOARD_PX + PAD * 2

NAVY_950 = (11, 18, 32)
NAVY_900 = (16, 24, 43)
NAVY_800 = (22, 31, 56)
NAVY_700 = (31, 42, 71)
GOLD = (224, 176, 78)
GOLD_SOFT = (243, 212, 147)
TEXT = (255, 255, 255)
TEXT_DIM = (195, 203, 220)
GREEN = (90, 168, 109)
RED = (226, 97, 93)
LIGHT_SQ = (240, 234, 214)
DARK_SQ = (111, 148, 87)
SEL = (255, 213, 90)


def _lighten(color, amt=18):
    return tuple(min(255, c + amt) for c in color)


class Button:
    def __init__(self, rect, label, bg=NAVY_800, fg=TEXT, active=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.bg = bg
        self.fg = fg
        self.active = active

    def draw(self, surf, font, hovered=False):
        bg = GOLD if self.active else self.bg
        if hovered and not self.active:
            bg = _lighten(bg)
        fg = (26, 19, 6) if self.active else self.fg
        pygame.draw.rect(surf, bg, self.rect, border_radius=8)
        border = GOLD_SOFT if hovered else (255, 255, 255)
        pygame.draw.rect(surf, border, self.rect, 1, border_radius=8)
        txt = font.render(self.label, True, fg)
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.rect.collidepoint(pos)


class VantageChess:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption('Vantage Chess  (F11: toggle fullscreen)')
        # `self.window` is the real OS window (resizable / fullscreen).
        # `self.screen` is a fixed-size virtual canvas that everything is
        # drawn onto, then scaled+letterboxed into the real window each
        # frame. This keeps all the existing layout code (which assumes a
        # WIN_W x WIN_H surface) working unchanged at any window size.
        self.window = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        self.screen = pygame.Surface((WIN_W, WIN_H))
        self.fullscreen = False
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont('Georgia', 38, bold=True)
        self.font_h = pygame.font.SysFont('Segoe UI', 20, bold=True)
        self.font_label = pygame.font.SysFont('Segoe UI', 13, bold=True)
        self.font_text = pygame.font.SysFont('Segoe UI', 14)
        self.font_btn = pygame.font.SysFont('Segoe UI', 14, bold=True)
        self.font_piece = pygame.font.SysFont('Segoe UI Symbol', 52)
        self.font_piece_small = pygame.font.SysFont('Segoe UI Symbol', 22)
        self.font_code = pygame.font.SysFont('Consolas', 17, bold=True)

        self.state = 'start'   # 'start' | 'game'
        self.panel = 'menu'    # start-screen sub-panel: 'menu'|'ai'|'host'|'join'
        self.difficulty = 2
        self.side = 'w'
        self.two_player = False
        self.G = None
        self.ai_pending = False
        self.ai_timer = 0
        self.flash_msg = None
        self.flash_until = 0

        # ---- online play ----
        self.net_queue = queue.Queue()   # background threads post callbacks here
        self.created_code = None
        self.join_code_text = ''
        self.join_input_active = False
        self.online_status = ''
        self.host_waiting_for_opponent = False
        self.host_blob_ready = False
        self.online_poll_due = 0

        self.mouse_pos = (0, 0)
        self.cursor_visible = True
        self.cursor_blink_due = 0
        self.copy_flash_until = 0

        self._build_start_buttons()

    # ---------------- window / fullscreen ----------------
    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            info = pygame.display.Info()
            self.window = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)

    def _canvas_metrics(self):
        ww, wh = self.window.get_size()
        scale = max(0.0001, min(ww / WIN_W, wh / WIN_H))
        draw_w, draw_h = int(WIN_W * scale), int(WIN_H * scale)
        off_x, off_y = (ww - draw_w) // 2, (wh - draw_h) // 2
        return scale, off_x, off_y, draw_w, draw_h

    def _to_canvas_pos(self, pos):
        scale, off_x, off_y, _, _ = self._canvas_metrics()
        return ((pos[0] - off_x) / scale, (pos[1] - off_y) / scale)

    def _present(self):
        scale, off_x, off_y, draw_w, draw_h = self._canvas_metrics()
        self.window.fill((0, 0, 0))
        scaled = pygame.transform.smoothscale(self.screen, (draw_w, draw_h))
        self.window.blit(scaled, (off_x, off_y))
        pygame.display.flip()

    # ---------------- start screen ----------------
    def _draw_btn(self, btn):
        btn.draw(self.screen, self.font_btn, hovered=btn.hit(self.mouse_pos))

    def _build_start_buttons(self):
        self.fullscreen_btn = Button((WIN_W - 58 - 168, 16, 168, 30), '\u26f6 Fullscreen (F11)', bg=NAVY_700)
        cx = WIN_W // 2

        # --- menu panel: three mode cards ---
        card_w, card_h, gap = 260, 150, 18
        total = card_w * 3 + gap * 2
        x0 = cx - total // 2
        y0 = 190
        self.menu_cards = [
            (Button((x0, y0, card_w, card_h), '', bg=NAVY_700), 'ai',
             'Play vs AI', 'Choose a difficulty and play against the engine.'),
            (Button((x0 + (card_w + gap), y0, card_w, card_h), '', bg=NAVY_700), 'host',
             'Host Online Game', 'Create a game code and share it with a friend.'),
            (Button((x0 + 2 * (card_w + gap), y0, card_w, card_h), '', bg=NAVY_700), 'join',
             'Join Online Game', 'Paste a friend\u2019s code to join their match.'),
        ]
        self.menu_2p_btn = Button((cx - 160, y0 + card_h + 30, 320, 44),
                                   'Local 2-Player (Hot-seat)', bg=NAVY_700)

        # --- AI panel ---
        self.diff_buttons = []
        labels = [('Easy', 1), ('Normal', 2), ('Medium', 3), ('Hard', 4)]
        bw, bh, gap2 = 110, 40, 10
        total2 = bw * 4 + gap2 * 3
        x0b = cx - total2 // 2
        y = 250
        for i, (lab, val) in enumerate(labels):
            r = (x0b + i * (bw + gap2), y, bw, bh)
            self.diff_buttons.append((Button(r, lab, active=(val == self.difficulty)), val))

        self.side_buttons = []
        bw2 = 170
        x0c = cx - (bw2 * 2 + gap2) // 2
        y2 = y + bh + 50
        for i, (lab, val) in enumerate([('White', 'w'), ('Black', 'b')]):
            r = (x0c + i * (bw2 + gap2), y2, bw2, bh)
            self.side_buttons.append((Button(r, lab, active=(val == self.side)), val))

        y3 = y2 + bh + 30
        self.start_ai_btn = Button((cx - 160, y3, 320, 48), 'Start vs AI', bg=GOLD)
        self.back_btn_ai = Button((cx - 160, y3 + 64, 320, 40), 'Back', bg=NAVY_800)

        # --- Host panel ---
        self.host_code_rect = pygame.Rect(cx - 160, 264, 320, 60)
        self.copy_code_btn = Button((cx - 160, 332, 320, 38), 'Copy Code', bg=NAVY_700)
        self.host_enter_btn = Button((cx - 160, 378, 320, 48), 'Waiting for opponent\u2026', bg=NAVY_800)
        self.back_btn_host = Button((cx - 160, 434, 320, 40), 'Cancel', bg=NAVY_800)

        # --- Join panel ---
        self.join_input_rect = pygame.Rect(cx - 160, 260, 320, 50)
        self.paste_code_btn = Button((cx - 160, 318, 320, 36), 'Paste from Clipboard', bg=NAVY_700)
        self.join_btn = Button((cx - 160, 362, 320, 48), 'Join Game', bg=GOLD)
        self.back_btn_join = Button((cx - 160, 418, 320, 40), 'Cancel', bg=NAVY_800)

    def _reset_online_ui(self):
        self.created_code = None
        self.join_code_text = ''
        self.online_status = ''
        self.host_waiting_for_opponent = False
        self.host_blob_ready = False
        self.join_input_active = False
        self.copy_code_btn.label = 'Copy Code'
        self.copy_flash_until = 0

    def draw_start(self):
        self.screen.fill(NAVY_950)
        pygame.draw.rect(self.screen, NAVY_900, (40, 40, WIN_W - 80, WIN_H - 80), border_radius=18)

        title = self.font_title.render('VANTAGE CHESS', True, GOLD_SOFT)
        self.screen.blit(title, title.get_rect(center=(WIN_W // 2, 100)))
        sub = self.font_text.render('Play a tuned AI, pass-the-keyboard locally, or play live online.',
                                     True, TEXT_DIM)
        self.screen.blit(sub, sub.get_rect(center=(WIN_W // 2, 135)))

        self._draw_btn(self.fullscreen_btn)

        if self.panel == 'menu':
            self._draw_menu_panel()
        elif self.panel == 'ai':
            self._draw_ai_panel()
        elif self.panel == 'host':
            self._draw_host_panel()
        elif self.panel == 'join':
            self._draw_join_panel()

    def _draw_menu_panel(self):
        for btn, key, heading, desc in self.menu_cards:
            hovered = btn.hit(self.mouse_pos)
            bg = _lighten(btn.bg) if hovered else btn.bg
            pygame.draw.rect(self.screen, bg, btn.rect, border_radius=12)
            border = GOLD if hovered else (255, 255, 255)
            pygame.draw.rect(self.screen, border, btn.rect, 2 if hovered else 1, border_radius=12)
            h = self.font_h.render(heading, True, GOLD_SOFT)
            self.screen.blit(h, (btn.rect.x + 16, btn.rect.y + 16))
            words = desc.split(' ')
            lines, line = [], ''
            for w in words:
                test = (line + ' ' + w).strip()
                if self.font_text.size(test)[0] > btn.rect.w - 32:
                    lines.append(line)
                    line = w
                else:
                    line = test
            if line:
                lines.append(line)
            ty = btn.rect.y + 50
            for ln in lines:
                t = self.font_text.render(ln, True, TEXT_DIM)
                self.screen.blit(t, (btn.rect.x + 16, ty))
                ty += 18
        self._draw_btn(self.menu_2p_btn)

    def _draw_ai_panel(self):
        lbl = self.font_label.render('DIFFICULTY', True, TEXT_DIM)
        self.screen.blit(lbl, (self.diff_buttons[0][0].rect.x, 220))
        for btn, _ in self.diff_buttons:
            self._draw_btn(btn)

        lbl2 = self.font_label.render('PLAY AS', True, TEXT_DIM)
        self.screen.blit(lbl2, (self.side_buttons[0][0].rect.x, self.side_buttons[0][0].rect.y - 24))
        for btn, _ in self.side_buttons:
            self._draw_btn(btn)

        self._draw_btn(self.start_ai_btn)
        self._draw_btn(self.back_btn_ai)

    def _draw_host_panel(self):
        lbl = self.font_label.render('YOUR GAME CODE  (click to copy)', True, TEXT_DIM)
        self.screen.blit(lbl, lbl.get_rect(center=(WIN_W // 2, 236)))
        hovered_code = self.host_code_rect.collidepoint(self.mouse_pos) and self.created_code
        pygame.draw.rect(self.screen, _lighten(NAVY_800) if hovered_code else NAVY_800,
                          self.host_code_rect, border_radius=10)
        pygame.draw.rect(self.screen, GOLD_SOFT if hovered_code else (255, 255, 255),
                          self.host_code_rect, 1, border_radius=10)
        code_text = self.created_code or 'Creating\u2026'
        max_w = self.host_code_rect.w - 24
        if self.font_code.size(code_text)[0] <= max_w:
            lines = [code_text]
        else:
            # wrap a long jsonblob id onto two lines, breaking at a hyphen if possible
            mid = len(code_text) // 2
            split_at = code_text.rfind('-', 0, mid + 4)
            if split_at == -1:
                split_at = mid
            else:
                split_at += 1
            lines = [code_text[:split_at], code_text[split_at:]]
        line_h = self.font_code.get_height()
        top = self.host_code_rect.centery - (len(lines) * line_h) // 2
        for i, ln in enumerate(lines):
            t = self.font_code.render(ln, True, GOLD_SOFT)
            self.screen.blit(t, t.get_rect(center=(self.host_code_rect.centerx, top + i * line_h + line_h // 2)))

        self._draw_btn(self.copy_code_btn)

        self.host_enter_btn.active = self.host_blob_ready
        self.host_enter_btn.label = ('Opponent joined \u2014 Enter Game'
                                      if self.host_blob_ready else 'Waiting for opponent\u2026')
        self._draw_btn(self.host_enter_btn)
        self._draw_btn(self.back_btn_host)

        if self.online_status:
            st = self.font_text.render(self.online_status, True, TEXT_DIM)
            self.screen.blit(st, st.get_rect(center=(WIN_W // 2, 512)))

        hint = self.font_text.render('Send this code to your friend \u2014 they paste it into "Join Online Game".',
                                      True, TEXT_DIM)
        self.screen.blit(hint, hint.get_rect(center=(WIN_W // 2, 486)))

    def _draw_join_panel(self):
        lbl = self.font_label.render('ENTER GAME CODE', True, TEXT_DIM)
        self.screen.blit(lbl, lbl.get_rect(center=(WIN_W // 2, 232)))
        box_color = GOLD if self.join_input_active else NAVY_800
        pygame.draw.rect(self.screen, NAVY_800, self.join_input_rect, border_radius=10)
        pygame.draw.rect(self.screen, box_color, self.join_input_rect, 2, border_radius=10)
        shown = self.join_code_text or ''
        font_for_code = self.font_code if self.font_code.size(shown)[0] <= self.join_input_rect.w - 20 else self.font_label
        t = font_for_code.render(shown, True, TEXT)
        text_rect = t.get_rect(center=self.join_input_rect.center)
        self.screen.blit(t, text_rect)
        if self.join_input_active and self.cursor_visible:
            cx = text_rect.right + 3 if shown else self.join_input_rect.centerx
            pygame.draw.line(self.screen, GOLD_SOFT,
                              (cx, self.join_input_rect.y + 12), (cx, self.join_input_rect.bottom - 12), 2)
        if not shown and not self.join_input_active:
            hint_t = self.font_text.render('Click here, then type or Ctrl+V to paste', True, TEXT_DIM)
            self.screen.blit(hint_t, hint_t.get_rect(center=self.join_input_rect.center))

        self._draw_btn(self.paste_code_btn)
        self._draw_btn(self.join_btn)
        self._draw_btn(self.back_btn_join)

        if self.online_status:
            st = self.font_text.render(self.online_status, True, TEXT_DIM)
            self.screen.blit(st, st.get_rect(center=(WIN_W // 2, 478)))

    def handle_start_click(self, pos):
        if self.fullscreen_btn.hit(pos):
            self.toggle_fullscreen()
            return

        if self.panel == 'menu':
            for btn, key, *_ in self.menu_cards:
                if btn.hit(pos):
                    self.panel = key
                    self._reset_online_ui()
                    if key == 'host':
                        self.begin_host_game()
                    elif key == 'join':
                        self.join_input_active = True
                    return
            if self.menu_2p_btn.hit(pos):
                self.two_player = True
                self.side = 'w'
                self.start_game()
                return
            return

        if self.panel == 'ai':
            for btn, val in self.diff_buttons:
                if btn.hit(pos):
                    self.difficulty = val
                    for b2, _ in self.diff_buttons:
                        b2.active = (b2 is btn)
                    return
            for btn, val in self.side_buttons:
                if btn.hit(pos):
                    self.side = val
                    for b2, _ in self.side_buttons:
                        b2.active = (b2 is btn)
                    return
            if self.start_ai_btn.hit(pos):
                self.two_player = False
                self.start_game()
                return
            if self.back_btn_ai.hit(pos):
                self.panel = 'menu'
                return
            return

        if self.panel == 'host':
            if (self.copy_code_btn.hit(pos) or self.host_code_rect.collidepoint(pos)) and self.created_code:
                self.do_copy_code()
                return
            if self.host_enter_btn.hit(pos) and self.host_blob_ready:
                self.enter_online_game(role='host', color='w', code=self.created_code)
                return
            if self.back_btn_host.hit(pos):
                self.panel = 'menu'
                self._reset_online_ui()
                return
            return

        if self.panel == 'join':
            if self.join_input_rect.collidepoint(pos):
                self.join_input_active = True
                return
            if self.paste_code_btn.hit(pos):
                self.do_paste_code()
                self.join_input_active = True
                return
            self.join_input_active = False
            if self.join_btn.hit(pos):
                self.submit_join_code()
                return
            if self.back_btn_join.hit(pos):
                self.panel = 'menu'
                self._reset_online_ui()
                return
            return

    def handle_start_keydown(self, event):
        if self.panel != 'join' or not self.join_input_active:
            return
        mods = pygame.key.get_mods()
        ctrl_held = mods & (pygame.KMOD_CTRL | pygame.KMOD_META)
        if ctrl_held and event.key == pygame.K_v:
            self.do_paste_code()
            return
        if event.key == pygame.K_BACKSPACE:
            self.join_code_text = self.join_code_text[:-1]
        elif event.key == pygame.K_RETURN:
            self.submit_join_code()
        else:
            ch = event.unicode
            if ch and ch.isprintable() and len(self.join_code_text) < 60:
                self.join_code_text += ch

    # ---------------- clipboard ----------------
    def do_copy_code(self):
        if not self.created_code:
            return
        ok = clipboard_copy(self.created_code)
        self.copy_code_btn.label = 'Copied!' if ok else 'Copy failed \u2014 select manually'
        self.copy_flash_until = pygame.time.get_ticks() + 1600

    def do_paste_code(self):
        text = clipboard_paste()
        if not text:
            return
        code = text.strip()
        if '/' in code:
            code = code.rstrip('/').split('/')[-1]
        self.join_code_text = code[:60]

    # ---------------- online: host ----------------
    def begin_host_game(self):
        self.copy_code_btn.label = 'Copy Code'
        self.copy_flash_until = 0
        self.created_code = None
        self.host_blob_ready = False
        self.online_status = 'Creating online game\u2026'

        initial = {
            'boardFEN': serialize_board(initial_board()),
            'turn': 'w', 'enPassant': None, 'history': [], 'captured': {'w': [], 'b': []},
            'status': 'normal', 'version': 0, 'whiteJoined': True, 'blackJoined': False,
            'resigned': None,
        }

        def worker():
            try:
                code = relay_create(initial)
            except Exception as e:
                self.net_queue.put(lambda: self._host_error(str(e)))
                return
            self.net_queue.put(lambda: self._host_created(code))

        threading.Thread(target=worker, daemon=True).start()

    def _host_created(self, code):
        self.created_code = code
        self.online_status = ''
        self._poll_host_for_join()

    def _host_error(self, msg):
        self.online_status = f'Connection failed: {msg}'

    def _poll_host_for_join(self):
        if self.panel != 'host' or not self.created_code or self.host_blob_ready:
            return
        code = self.created_code

        def worker():
            try:
                r = relay_get(code)
            except Exception:
                r = None
            self.net_queue.put(lambda: self._host_poll_result(r))

        threading.Thread(target=worker, daemon=True).start()

    def _host_poll_result(self, r):
        if r and r.get('blackJoined'):
            self.host_blob_ready = True
        if self.panel == 'host' and not self.host_blob_ready:
            self.online_poll_due = pygame.time.get_ticks() + 1500

    # ---------------- online: join ----------------
    def submit_join_code(self):
        code = self.join_code_text.strip()
        if '/' in code:
            code = code.rstrip('/').split('/')[-1]
        if not code:
            self.online_status = 'Enter a game code first.'
            return
        self.online_status = 'Connecting\u2026'

        def worker():
            try:
                r = relay_get(code)
            except Exception as e:
                self.net_queue.put(lambda: self._join_error(str(e)))
                return
            if not r:
                self.net_queue.put(lambda: self._join_error('Game code not found.'))
                return
            if r.get('blackJoined'):
                self.net_queue.put(lambda: self._join_error('That game already has two players.'))
                return
            r['blackJoined'] = True
            try:
                relay_set(code, r)
            except Exception as e:
                self.net_queue.put(lambda: self._join_error(str(e)))
                return
            self.net_queue.put(lambda: self.enter_online_game(role='guest', color='b', code=code, initial_state=r))

        threading.Thread(target=worker, daemon=True).start()

    def _join_error(self, msg):
        self.online_status = msg

    def enter_online_game(self, role, color, code, initial_state=None):
        self.G = {
            'board': initial_board(),
            'turn': 'w',
            'enPassant': None,
            'selected': None,
            'legalForSelected': [],
            'lastMove': None,
            'history': [],
            'captured': {'w': [], 'b': []},
            'status': 'normal',
            'playerColor': color,
            'aiDifficulty': self.difficulty,
            'gameOver': False,
            'resigned': None,
            'mode': 'online',
            'roomCode': code,
            'isHost': (role == 'host'),
            'version': 0,
        }
        if initial_state:
            load_state_from_relay(self.G, initial_state)
        self.two_player = False
        self.state = 'game'
        self._build_game_buttons()
        self.online_poll_due = pygame.time.get_ticks() + 1200

    def poll_online_state(self):
        G = self.G
        if not G or G.get('mode') != 'online':
            return
        code = G['roomCode']

        def worker():
            try:
                r = relay_get(code)
            except Exception:
                r = None
            self.net_queue.put(lambda: self._apply_online_poll(r))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_online_poll(self, r):
        G = self.G
        if not G or G.get('mode') != 'online' or not r:
            return
        if r.get('version', 0) != G['version']:
            load_state_from_relay(G, r)

    def push_online_state(self):
        G = self.G
        if not G or G.get('mode') != 'online':
            return
        G['version'] += 1
        payload = serialize_state_for_relay(G)
        code = G['roomCode']

        def worker():
            try:
                relay_set(code, payload)
            except Exception:
                pass  # best-effort; next poll resyncs

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- game state ----------------
    def start_game(self):
        self.G = {
            'board': initial_board(),
            'turn': 'w',
            'enPassant': None,
            'selected': None,
            'legalForSelected': [],
            'lastMove': None,
            'history': [],
            'captured': {'w': [], 'b': []},
            'status': 'normal',
            'playerColor': self.side,
            'aiDifficulty': self.difficulty,
            'gameOver': False,
            'resigned': None,
            'mode': ('local2p' if self.two_player else 'ai'),
        }
        self.state = 'game'
        self._build_game_buttons()
        if not self.two_player and self.G['turn'] != self.G['playerColor']:
            self.ai_pending = True
            self.ai_timer = pygame.time.get_ticks() + 400

    def _build_game_buttons(self):
        sb_x = PAD + BOARD_PX + PAD
        y = PAD + BOARD_PX - 50
        self.resign_btn = Button((sb_x, y, (SIDEBAR_W - 10) // 2, 42), 'Resign', bg=RED)
        self.newgame_btn = Button((sb_x + (SIDEBAR_W - 10) // 2 + 10, y, (SIDEBAR_W - 10) // 2, 42),
                                   'New Game', bg=GOLD)
        self.close_overlay_btn = Button((WIN_W // 2 - 90, WIN_H // 2 + 40, 180, 44), 'Close', bg=GOLD)

    # ---------------- game logic glue ----------------
    def apply_and_advance(self, move):
        G = self.G
        piece = G['board'][move['from'][0]][move['from'][1]]
        state = {'enPassant': G['enPassant']}
        nb, ns = apply_move(G['board'], state, move)

        if move.get('captured'):
            G['captured'][piece['color']].append(move['captured']['type'])

        G['history'].append(move_notation(move, piece))
        G['board'] = nb
        G['enPassant'] = ns['enPassant']
        G['turn'] = 'b' if G['turn'] == 'w' else 'w'
        G['lastMove'] = move
        G['selected'] = None
        G['legalForSelected'] = []

        G['status'] = game_status(G['board'], {'enPassant': G['enPassant']}, G['turn'])
        if G['status'] in ('checkmate', 'stalemate'):
            G['gameOver'] = True

    def make_human_move(self, move):
        self.apply_and_advance(move)
        G = self.G
        if G.get('mode') == 'online':
            self.push_online_state()
        elif G.get('mode') == 'ai' and not G['gameOver']:
            self.ai_pending = True
            self.ai_timer = pygame.time.get_ticks() + 350

    def ai_turn(self):
        G = self.G
        if not G or G['gameOver']:
            return
        state = {'enPassant': G['enPassant']}
        move = pick_ai_move(G['board'], state, G['turn'], G['aiDifficulty'])
        if move:
            self.apply_and_advance(move)

    def resign_game(self):
        if not self.G or self.G['gameOver']:
            return
        self.G['resigned'] = self.G['turn']
        self.G['gameOver'] = True
        if self.G.get('mode') == 'online':
            self.push_online_state()

    def status_text(self):
        G = self.G
        if G['resigned']:
            return ('White' if G['resigned'] == 'w' else 'Black') + ' resigned'
        if G['status'] == 'checkmate':
            return ('Black' if G['turn'] == 'w' else 'White') + ' wins by checkmate'
        if G['status'] == 'stalemate':
            return 'Draw by stalemate'
        return ''

    # ---------------- input on board ----------------
    def board_cell_at(self, pos):
        x, y = pos
        bx, by = PAD, PAD
        if not (bx <= x < bx + BOARD_PX and by <= y < by + BOARD_PX):
            return None
        col = (x - bx) // SQ
        row = (y - by) // SQ
        flip = (self.G.get('mode') != 'local2p') and self.G['playerColor'] == 'b'
        if flip:
            row, col = 7 - row, 7 - col
        return int(row), int(col)

    def on_square_click(self, r, c):
        G = self.G
        if not G or G['gameOver'] or self.ai_pending:
            return
        mode = G.get('mode')
        if mode in ('ai', 'online') and G['turn'] != G['playerColor']:
            return

        piece = G['board'][r][c]
        if G['selected']:
            move = next((m for m in G['legalForSelected'] if m['to'] == (r, c)), None)
            if move:
                self.make_human_move(move)
                return

        if piece and piece['color'] == G['turn']:
            G['selected'] = (r, c)
            state = {'enPassant': G['enPassant']}
            moves = legal_moves(G['board'], G['turn'], state)
            G['legalForSelected'] = [m for m in moves if m['from'] == (r, c)]
        else:
            G['selected'] = None
            G['legalForSelected'] = []

    # ---------------- drawing ----------------
    def draw_game(self):
        self.screen.fill(NAVY_950)
        self.draw_board()
        self.draw_sidebar()
        self._draw_btn(self.fullscreen_btn)
        if self.G['gameOver']:
            self.draw_overlay()

    def draw_board(self):
        G = self.G
        bx, by = PAD, PAD
        flip = (G.get('mode') != 'local2p') and (G['playerColor'] == 'b')

        pygame.draw.rect(self.screen, GOLD, (bx - 4, by - 4, BOARD_PX + 8, BOARD_PX + 8), border_radius=6)

        for disp_r in range(8):
            for disp_c in range(8):
                r = 7 - disp_r if flip else disp_r
                c = 7 - disp_c if flip else disp_c
                x = bx + disp_c * SQ
                y = by + disp_r * SQ
                light = (r + c) % 2 == 0
                color = LIGHT_SQ if light else DARK_SQ
                pygame.draw.rect(self.screen, color, (x, y, SQ, SQ))

                last = G['lastMove']
                if last and ((last['from'] == (r, c)) or (last['to'] == (r, c))):
                    pygame.draw.rect(self.screen, (*GOLD, 255), (x, y, SQ, SQ), 4)

                if G['selected'] == (r, c):
                    pygame.draw.rect(self.screen, SEL, (x, y, SQ, SQ), 5)

                piece = G['board'][r][c]
                if piece:
                    glyph = PIECE_GLYPH[piece['color']][piece['type']]
                    fg = (255, 255, 255) if piece['color'] == 'w' else (26, 26, 26)
                    outline = (40, 40, 40) if piece['color'] == 'w' else (0, 0, 0)
                    txt = self.font_piece.render(glyph, True, fg)
                    rect = txt.get_rect(center=(x + SQ // 2, y + SQ // 2))
                    self.screen.blit(txt, rect)
                    if piece['type'] == 'k' and is_in_check(G['board'], piece['color']):
                        pygame.draw.rect(self.screen, RED, (x, y, SQ, SQ), 5)

                target = next((m for m in G['legalForSelected'] if m['to'] == (r, c)), None)
                if target:
                    cx, cy = x + SQ // 2, y + SQ // 2
                    if target.get('captured'):
                        pygame.draw.circle(self.screen, RED, (cx, cy), 33, 5)
                    else:
                        pygame.draw.circle(self.screen, (20, 20, 20), (cx, cy), 11)

    def draw_sidebar(self):
        G = self.G
        sb_x = PAD + BOARD_PX + PAD
        y = PAD

        # turn banner
        banner_rect = pygame.Rect(sb_x, y, SIDEBAR_W, 46)
        pygame.draw.rect(self.screen, NAVY_800, banner_rect, border_radius=10)
        if G['gameOver']:
            txt = self.status_text()
        else:
            txt = ('White' if G['turn'] == 'w' else 'Black') + ' to move'
            if G['status'] == 'check':
                txt += ' — Check!'
        t = self.font_h.render(txt, True, GOLD_SOFT)
        self.screen.blit(t, t.get_rect(center=banner_rect.center))
        y += 46 + 14

        if self.ai_pending:
            think_rect = pygame.Rect(sb_x, y, SIDEBAR_W, 36)
            pygame.draw.rect(self.screen, NAVY_700, think_rect, border_radius=10)
            t = self.font_text.render('AI is thinking…', True, GOLD_SOFT)
            self.screen.blit(t, t.get_rect(center=think_rect.center))
            y += 36 + 14

        if G.get('mode') == 'online':
            room_rect = pygame.Rect(sb_x, y, SIDEBAR_W, 36)
            pygame.draw.rect(self.screen, NAVY_700, room_rect, border_radius=10)
            you = 'White' if G['playerColor'] == 'w' else 'Black'
            t = self.font_text.render(f'Room {G["roomCode"]}  \u00b7  You are {you}', True, GOLD_SOFT)
            self.screen.blit(t, t.get_rect(center=room_rect.center))
            y += 36 + 14

        # captured
        cap_rect = pygame.Rect(sb_x, y, SIDEBAR_W, 90)
        pygame.draw.rect(self.screen, NAVY_700, cap_rect, border_radius=10)
        lbl = self.font_label.render('CAPTURED BY WHITE', True, TEXT_DIM)
        self.screen.blit(lbl, (sb_x + 14, y + 10))
        gw = ' '.join(PIECE_GLYPH['b'][t] for t in G['captured']['w']) or '—'
        txt = self.font_piece_small.render(gw, True, TEXT)
        self.screen.blit(txt, (sb_x + 14, y + 28))
        lbl2 = self.font_label.render('CAPTURED BY BLACK', True, TEXT_DIM)
        self.screen.blit(lbl2, (sb_x + 14, y + 56))
        gb = ' '.join(PIECE_GLYPH['w'][t] for t in G['captured']['b']) or '—'
        txt2 = self.font_piece_small.render(gb, True, TEXT)
        self.screen.blit(txt2, (sb_x + 14, y + 74))
        y += 90 + 14

        # move history
        hist_h = self.resign_btn.rect.y - 14 - y
        hist_rect = pygame.Rect(sb_x, y, SIDEBAR_W, max(hist_h, 60))
        pygame.draw.rect(self.screen, NAVY_700, hist_rect, border_radius=10)
        lbl3 = self.font_label.render('MOVE HISTORY', True, TEXT_DIM)
        self.screen.blit(lbl3, (sb_x + 14, y + 10))
        hy = y + 32
        line_h = 20
        max_lines = (hist_rect.height - 36) // line_h
        hist = G['history']
        pairs = [(i // 2 + 1, hist[i] if i < len(hist) else '', hist[i + 1] if i + 1 < len(hist) else '')
                  for i in range(0, len(hist), 2)]
        start_idx = max(0, len(pairs) - max_lines)
        for num, wmove, bmove in pairs[start_idx:]:
            line = f'{num}. {wmove} {bmove}'
            t = self.font_text.render(line, True, TEXT_DIM)
            self.screen.blit(t, (sb_x + 14, hy))
            hy += line_h

        self._draw_btn(self.resign_btn)
        self._draw_btn(self.newgame_btn)

    def draw_overlay(self):
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((5, 8, 16, 190))
        self.screen.blit(overlay, (0, 0))

        card = pygame.Rect(WIN_W // 2 - 220, WIN_H // 2 - 90, 440, 220)
        pygame.draw.rect(self.screen, NAVY_800, card, border_radius=16)
        pygame.draw.rect(self.screen, GOLD, card, 2, border_radius=16)

        title = self.status_text() or 'Game Over'
        t = self.font_h.render(title, True, GOLD_SOFT)
        self.screen.blit(t, t.get_rect(center=(card.centerx, card.y + 50)))
        sub = self.font_text.render('Thanks for playing Vantage Chess.', True, TEXT_DIM)
        self.screen.blit(sub, sub.get_rect(center=(card.centerx, card.y + 85)))

        self._draw_btn(self.close_overlay_btn)

    # ---------------- main loop ----------------
    def back_to_start(self):
        self.G = None
        self.state = 'start'
        self.panel = 'menu'
        self._reset_online_ui()

    def _drain_net_queue(self):
        while True:
            try:
                cb = self.net_queue.get_nowait()
            except queue.Empty:
                break
            try:
                cb()
            except Exception:
                pass

    def run(self):
        running = True
        while running:
            now = pygame.time.get_ticks()
            self.mouse_pos = self._to_canvas_pos(pygame.mouse.get_pos())
            self._drain_net_queue()

            if self.copy_flash_until and now >= self.copy_flash_until:
                self.copy_code_btn.label = 'Copy Code'
                self.copy_flash_until = 0

            if now >= self.cursor_blink_due:
                self.cursor_visible = not self.cursor_visible
                self.cursor_blink_due = now + 500

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                    self.window = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                        continue
                    if event.key == pygame.K_ESCAPE and self.fullscreen:
                        self.toggle_fullscreen()
                        continue
                    if self.state == 'start':
                        self.handle_start_keydown(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    pos = self._to_canvas_pos(event.pos)
                    if self.state == 'start':
                        self.handle_start_click(pos)
                    elif self.state == 'game':
                        G = self.G
                        if self.fullscreen_btn.hit(pos):
                            self.toggle_fullscreen()
                            continue
                        if G['gameOver']:
                            if self.close_overlay_btn.hit(pos):
                                self.back_to_start()
                            continue
                        if self.resign_btn.hit(pos):
                            self.resign_game()
                            continue
                        if self.newgame_btn.hit(pos):
                            self.back_to_start()
                            continue
                        cell = self.board_cell_at(pos)
                        if cell:
                            self.on_square_click(*cell)

            if self.state == 'game' and self.ai_pending and now >= self.ai_timer:
                self.ai_pending = False
                self.ai_turn()

            # online: host waiting-room polling for an opponent
            if (self.state == 'start' and self.panel == 'host' and self.created_code
                    and not self.host_blob_ready and now >= self.online_poll_due):
                self.online_poll_due = now + 1_000_000_000  # avoid re-fire until result lands
                self._poll_host_for_join()

            # online: in-game polling for opponent moves
            if (self.state == 'game' and self.G and self.G.get('mode') == 'online'
                    and not self.G['gameOver'] and now >= self.online_poll_due):
                self.online_poll_due = now + 1500
                self.poll_online_state()

            if self.state == 'start':
                self.draw_start()
            else:
                self.draw_game()

            self._present()
            self.clock.tick(60)

        pygame.quit()
        sys.exit()


if __name__ == '__main__':
    VantageChess().run()
