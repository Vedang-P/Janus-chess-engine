"""Handcrafted centipawn evaluation with explainable breakdowns."""

from __future__ import annotations

from dataclasses import dataclass

from .bitboards import iter_bits
from .board import Board
from .constants import (
    BLACK,
    BLACK_PIECES,
    BB,
    BK,
    BN,
    BP,
    BQ,
    BR,
    PIECE_SYMBOLS,
    PIECE_NONE,
    WHITE,
    WHITE_PIECES,
    WB,
    WK,
    WN,
    WP,
    WQ,
    WR,
    square_name,
)
from .movegen import (
    BISHOP_RAY_KEYS,
    KING_ATTACKS,
    KNIGHT_ATTACKS,
    PAWN_ATTACKS,
    QUEEN_RAY_KEYS,
    ROOK_RAY_KEYS,
    RAYS,
    is_square_attacked,
    king_square,
)

# Material values (centipawns).
PIECE_VALUES = {
    WP: 100,
    WN: 320,
    WB: 330,
    WR: 500,
    WQ: 900,
    WK: 0,
}

# Piece-square tables for white; mirrored for black.
PAWN_PST = (
    0, 0, 0, 0, 0, 0, 0, 0,
    8, 10, 10, -12, -12, 10, 10, 8,
    5, 6, 8, 14, 14, 8, 6, 5,
    4, 5, 8, 24, 24, 8, 5, 4,
    2, 3, 7, 20, 20, 7, 3, 2,
    1, 1, 3, 10, 10, 3, 1, 1,
    0, 0, -6, -6, -6, -6, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
)

KNIGHT_PST = (
    -45, -25, -20, -18, -18, -20, -25, -45,
    -20, -4, 2, 6, 6, 2, -4, -20,
    -10, 4, 10, 14, 14, 10, 4, -10,
    -8, 8, 15, 18, 18, 15, 8, -8,
    -8, 8, 15, 18, 18, 15, 8, -8,
    -10, 4, 10, 14, 14, 10, 4, -10,
    -20, -4, 2, 6, 6, 2, -4, -20,
    -45, -25, -20, -18, -18, -20, -25, -45,
)

BISHOP_PST = (
    -18, -8, -8, -8, -8, -8, -8, -18,
    -8, 5, 2, 2, 2, 2, 5, -8,
    -6, 2, 8, 8, 8, 8, 2, -6,
    -4, 5, 8, 12, 12, 8, 5, -4,
    -4, 5, 8, 12, 12, 8, 5, -4,
    -6, 2, 8, 8, 8, 8, 2, -6,
    -8, 5, 2, 2, 2, 2, 5, -8,
    -18, -8, -8, -8, -8, -8, -8, -18,
)

ROOK_PST = (
    0, 4, 4, 7, 7, 4, 4, 0,
    -2, 0, 0, 2, 2, 0, 0, -2,
    -2, 0, 0, 2, 2, 0, 0, -2,
    -2, 0, 0, 2, 2, 0, 0, -2,
    -2, 0, 0, 2, 2, 0, 0, -2,
    -2, 0, 0, 2, 2, 0, 0, -2,
    5, 9, 9, 11, 11, 9, 9, 5,
    0, 4, 4, 7, 7, 4, 4, 0,
)

QUEEN_PST = (
    -10, -6, -4, -2, -2, -4, -6, -10,
    -6, -2, 0, 1, 1, 0, -2, -6,
    -4, 0, 1, 2, 2, 1, 0, -4,
    -2, 1, 2, 3, 3, 2, 1, -2,
    -2, 1, 2, 3, 3, 2, 1, -2,
    -4, 0, 1, 2, 2, 1, 0, -4,
    -6, -2, 0, 1, 1, 0, -2, -6,
    -10, -6, -4, -2, -2, -4, -6, -10,
)

KING_PST = (
    12, 24, 8, -6, -6, 8, 24, 12,
    12, 18, 2, -8, -8, 2, 18, 12,
    8, 10, -4, -12, -12, -4, 10, 8,
    3, 2, -9, -16, -16, -9, 2, 3,
    -2, -6, -12, -20, -20, -12, -6, -2,
    -10, -12, -16, -22, -22, -16, -12, -10,
    -15, -14, -14, -14, -14, -14, -14, -15,
    -20, -16, -12, -10, -10, -12, -16, -20,
)

PST_BY_KIND = {
    WP: PAWN_PST,
    WN: KNIGHT_PST,
    WB: BISHOP_PST,
    WR: ROOK_PST,
    WQ: QUEEN_PST,
    WK: KING_PST,
}

MOBILITY_WEIGHT = {
    WP: 1,
    WN: 4,
    WB: 5,
    WR: 2,
    WQ: 1,
    WK: 1,
}


@dataclass(slots=True)
class EvalDetails:
    score_cp: int
    score: float
    white_minus_black: int
    components: dict[str, dict[str, int]]
    piece_values: dict[str, int]
    piece_breakdown: dict[str, dict[str, int | str]]
    heatmap: dict[str, int]


def _mirror_sq(square: int) -> int:
    file_idx = square % 8
    rank_idx = square // 8
    return (7 - rank_idx) * 8 + file_idx


def _piece_side(piece: int) -> int:
    return WHITE if piece < BP else BLACK


def _piece_kind(piece: int) -> int:
    return piece if piece < BP else piece - 6


def _mobility_targets(board: Board, piece: int, square: int, side: int) -> int:
    own_occ = board.occupancies[side]

    if piece in (WN, BN):
        return (KNIGHT_ATTACKS[square] & ~own_occ).bit_count()
    if piece in (WK, BK):
        return (KING_ATTACKS[square] & ~own_occ).bit_count()

    ray_keys: tuple[str, ...]
    if piece in (WB, BB):
        ray_keys = BISHOP_RAY_KEYS
    elif piece in (WR, BR):
        ray_keys = ROOK_RAY_KEYS
    elif piece in (WQ, BQ):
        ray_keys = QUEEN_RAY_KEYS
    else:
        # Pawns are handled directly in pressure maps and structure terms.
        return 0

    count = 0
    own_set = WHITE_PIECES if side == WHITE else BLACK_PIECES
    for key in ray_keys:
        for target in RAYS[key][square]:
            occupant = board.piece_on(target)
            if occupant == PIECE_NONE:
                count += 1
                continue
            if occupant not in own_set:
                count += 1
            break
    return count


def _pawn_structure_terms(board: Board) -> dict[int, dict[int, int]]:
    terms: dict[int, dict[int, int]] = {WHITE: {}, BLACK: {}}

    for side, pawn_piece in ((WHITE, WP), (BLACK, BP)):
        pawns = list(iter_bits(board.piece_bitboards[pawn_piece]))
        enemy_pawns = list(iter_bits(board.piece_bitboards[BP if side == WHITE else WP]))

        pawns_by_file: dict[int, list[int]] = {file_idx: [] for file_idx in range(8)}
        enemy_by_file: dict[int, list[int]] = {file_idx: [] for file_idx in range(8)}

        for sq in pawns:
            pawns_by_file[sq % 8].append(sq)
        for sq in enemy_pawns:
            enemy_by_file[sq % 8].append(sq)

        for sq in pawns:
            file_idx = sq % 8
            rank_idx = sq // 8
            delta = 0

            if len(pawns_by_file[file_idx]) > 1:
                delta -= 14

            has_adjacent_friend = False
            for adj in (file_idx - 1, file_idx + 1):
                if 0 <= adj < 8 and pawns_by_file[adj]:
                    has_adjacent_friend = True
                    break
            if not has_adjacent_friend:
                delta -= 12

            blocked = False
            for ef in (file_idx - 1, file_idx, file_idx + 1):
                if not 0 <= ef < 8:
                    continue
                for enemy_sq in enemy_by_file[ef]:
                    enemy_rank = enemy_sq // 8
                    if side == WHITE and enemy_rank > rank_idx:
                        blocked = True
                        break
                    if side == BLACK and enemy_rank < rank_idx:
                        blocked = True
                        break
                if blocked:
                    break

            if not blocked:
                advance = rank_idx if side == WHITE else (7 - rank_idx)
                delta += 20 + advance * 6

            terms[side][sq] = delta

    return terms


def _king_safety_terms(board: Board) -> dict[int, dict[int, int]]:
    terms: dict[int, dict[int, int]] = {WHITE: {}, BLACK: {}}

    for side in (WHITE, BLACK):
        ksq = king_square(board, side)
        if ksq == -1:
            continue

        opp = BLACK if side == WHITE else WHITE
        own_pawn = WP if side == WHITE else BP

        shield = 0
        for offset in ((7, 8, 9) if side == WHITE else (-7, -8, -9)):
            target = ksq + offset
            if not 0 <= target < 64:
                continue
            if abs((target % 8) - (ksq % 8)) > 1:
                continue
            if board.piece_on(target) == own_pawn:
                shield += 6
            else:
                shield -= 8

        ring_penalty = 0
        ring = KING_ATTACKS[ksq] | (1 << ksq)
        for sq in iter_bits(ring):
            if is_square_attacked(board, sq, opp):
                ring_penalty -= 8

        terms[side][ksq] = shield + ring_penalty

    return terms


def _pressure_heatmap(board: Board) -> dict[str, int]:
    heat = [0] * 64

    def add_targets(mask: int, sign: int) -> None:
        for target in iter_bits(mask):
            heat[target] += sign

    for side, pieces in ((WHITE, WHITE_PIECES), (BLACK, BLACK_PIECES)):
        sign = 1 if side == WHITE else -1
        own_set = WHITE_PIECES if side == WHITE else BLACK_PIECES

        pawn_piece = WP if side == WHITE else BP
        for sq in iter_bits(board.piece_bitboards[pawn_piece]):
            add_targets(PAWN_ATTACKS[side][sq], sign)

        knight_piece = WN if side == WHITE else BN
        for sq in iter_bits(board.piece_bitboards[knight_piece]):
            add_targets(KNIGHT_ATTACKS[sq], sign)

        king_piece = WK if side == WHITE else BK
        for sq in iter_bits(board.piece_bitboards[king_piece]):
            add_targets(KING_ATTACKS[sq], sign)

        for piece, ray_keys in (
            (WB if side == WHITE else BB, BISHOP_RAY_KEYS),
            (WR if side == WHITE else BR, ROOK_RAY_KEYS),
            (WQ if side == WHITE else BQ, QUEEN_RAY_KEYS),
        ):
            for sq in iter_bits(board.piece_bitboards[piece]):
                for key in ray_keys:
                    for target in RAYS[key][sq]:
                        occupant = board.piece_on(target)
                        if occupant == PIECE_NONE:
                            heat[target] += sign
                            continue
                        if occupant not in own_set:
                            heat[target] += sign
                        break

    return {square_name(sq): val for sq, val in enumerate(heat) if val != 0}


def _evaluate(board: Board, collect_details: bool) -> tuple[int, dict | None]:
    components = {
        WHITE: {"material": 0, "pst": 0, "mobility": 0, "king_safety": 0, "pawn_structure": 0},
        BLACK: {"material": 0, "pst": 0, "mobility": 0, "king_safety": 0, "pawn_structure": 0},
    }

    piece_breakdown: dict[str, dict[str, int | str]] = {}
    piece_values: dict[str, int] = {}

    pawn_terms = _pawn_structure_terms(board)
    king_terms = _king_safety_terms(board)

    for piece, bb in enumerate(board.piece_bitboards):
        side = _piece_side(piece)
        kind = _piece_kind(piece)
        base = PIECE_VALUES[kind]
        pst_table = PST_BY_KIND[kind]
        mobility_weight = MOBILITY_WEIGHT[kind]

        for sq in iter_bits(bb):
            sq_key = square_name(sq)
            pst = pst_table[sq] if side == WHITE else pst_table[_mirror_sq(sq)]
            mobility = _mobility_targets(board, piece, sq, side) * mobility_weight
            pawn_structure = pawn_terms[side].get(sq, 0)
            king_safety = king_terms[side].get(sq, 0)
            total = base + pst + mobility + pawn_structure + king_safety

            components[side]["material"] += base
            components[side]["pst"] += pst
            components[side]["mobility"] += mobility
            components[side]["pawn_structure"] += pawn_structure
            components[side]["king_safety"] += king_safety

            if collect_details:
                signed_total = total if side == WHITE else -total
                piece_values[sq_key] = signed_total
                piece_breakdown[sq_key] = {
                    "piece": PIECE_SYMBOLS[piece],
                    "side": "w" if side == WHITE else "b",
                    "base": base,
                    "pst": pst,
                    "mobility": mobility,
                    "pawn_structure": pawn_structure,
                    "king_safety": king_safety,
                    "total": total,
                    "signed_total": signed_total,
                }

    white_total = sum(components[WHITE].values())
    black_total = sum(components[BLACK].values())
    white_minus_black = white_total - black_total
    score_cp = white_minus_black if board.side_to_move == WHITE else -white_minus_black

    if not collect_details:
        return score_cp, None

    net_components = {
        key: components[WHITE][key] - components[BLACK][key]
        for key in components[WHITE]
    }

    payload = {
        "score_cp": score_cp,
        "score": round(score_cp / 100.0, 2),
        "white_minus_black": white_minus_black,
        "components": {
            "white": components[WHITE],
            "black": components[BLACK],
            "net": net_components,
        },
        "piece_values": piece_values,
        "piece_breakdown": piece_breakdown,
        "heatmap": _pressure_heatmap(board),
    }
    return score_cp, payload


def evaluate(board: Board) -> int:
    """Return centipawn score from side-to-move perspective."""
    score_cp, _ = _evaluate(board, collect_details=False)
    return score_cp


def evaluate_detailed(board: Board) -> EvalDetails:
    """Return centipawn score plus per-piece explainability breakdown."""
    _, payload = _evaluate(board, collect_details=True)
    assert payload is not None
    return EvalDetails(
        score_cp=payload["score_cp"],
        score=payload["score"],
        white_minus_black=payload["white_minus_black"],
        components=payload["components"],
        piece_values=payload["piece_values"],
        piece_breakdown=payload["piece_breakdown"],
        heatmap=payload["heatmap"],
    )


def terminal_score(board: Board, side_to_move_in_check: bool, ply: int) -> int:
    if side_to_move_in_check:
        return -100_000 + ply
    return 0
