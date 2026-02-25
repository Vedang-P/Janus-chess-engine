"""Board representation with reversible make/unmake operations."""

from __future__ import annotations

from dataclasses import dataclass

from .bitboards import clear_bit, get_bit, set_bit
from .constants import (
    A1,
    A8,
    BLACK,
    BLACK_PIECES,
    BK,
    BOTH,
    BP,
    BR,
    C1,
    C8,
    CASTLE_BLACK_KING,
    CASTLE_BLACK_QUEEN,
    CASTLE_WHITE_KING,
    CASTLE_WHITE_QUEEN,
    D1,
    D8,
    E1,
    E8,
    F1,
    F8,
    G1,
    G8,
    H1,
    H8,
    PIECE_NONE,
    PIECE_SYMBOLS,
    START_FEN,
    SYMBOL_TO_PIECE,
    WHITE,
    WHITE_PIECES,
    WK,
    WP,
    WR,
    opposite,
    square_index,
    square_name,
)
from .move import Move


@dataclass(slots=True)
class UndoState:
    move: Move
    captured_piece: int
    castling_rights: int
    en_passant: int | None
    halfmove_clock: int
    fullmove_number: int


class Board:
    __slots__ = (
        "piece_bitboards",
        "occupancies",
        "side_to_move",
        "castling_rights",
        "en_passant",
        "halfmove_clock",
        "fullmove_number",
        "history",
    )

    def __init__(self, fen: str = START_FEN):
        self.piece_bitboards = [0] * 12
        self.occupancies = [0, 0, 0]
        self.side_to_move = WHITE
        self.castling_rights = 0
        self.en_passant: int | None = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.history: list[UndoState] = []
        self.set_fen(fen)

    def reset(self) -> None:
        self.piece_bitboards = [0] * 12
        self.occupancies = [0, 0, 0]
        self.side_to_move = WHITE
        self.castling_rights = 0
        self.en_passant = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.history.clear()

    def set_fen(self, fen: str) -> None:
        self.reset()
        fields = fen.split()
        if len(fields) != 6:
            raise ValueError(f"Invalid FEN: {fen}")

        placement, side, castling, ep, halfmove, fullmove = fields

        ranks = placement.split("/")
        if len(ranks) != 8:
            raise ValueError(f"Invalid FEN board placement: {placement}")

        for rank_idx, rank in enumerate(reversed(ranks)):
            file_idx = 0
            for ch in rank:
                if ch.isdigit():
                    file_idx += int(ch)
                    continue
                if ch not in SYMBOL_TO_PIECE:
                    raise ValueError(f"Invalid piece symbol in FEN: {ch}")
                sq = rank_idx * 8 + file_idx
                self.piece_bitboards[SYMBOL_TO_PIECE[ch]] = set_bit(
                    self.piece_bitboards[SYMBOL_TO_PIECE[ch]], sq
                )
                file_idx += 1
            if file_idx != 8:
                raise ValueError(f"Invalid rank in FEN: {rank}")

        self.side_to_move = WHITE if side == "w" else BLACK
        if side not in ("w", "b"):
            raise ValueError(f"Invalid side to move in FEN: {side}")

        self.castling_rights = 0
        if "K" in castling:
            self.castling_rights |= CASTLE_WHITE_KING
        if "Q" in castling:
            self.castling_rights |= CASTLE_WHITE_QUEEN
        if "k" in castling:
            self.castling_rights |= CASTLE_BLACK_KING
        if "q" in castling:
            self.castling_rights |= CASTLE_BLACK_QUEEN

        self.en_passant = None if ep == "-" else square_index(ep)
        self.halfmove_clock = int(halfmove)
        self.fullmove_number = int(fullmove)

        self._recompute_occupancies()

    def piece_on(self, square: int) -> int:
        for piece, bb in enumerate(self.piece_bitboards):
            if get_bit(bb, square):
                return piece
        return PIECE_NONE

    def make_move(self, move: Move) -> bool:
        from_sq = move.from_square
        to_sq = move.to_square
        moving_piece = move.piece

        if self.piece_on(from_sq) != moving_piece:
            return False
        if self.side_to_move == WHITE and moving_piece not in WHITE_PIECES:
            return False
        if self.side_to_move == BLACK and moving_piece not in BLACK_PIECES:
            return False

        target_piece = self.piece_on(to_sq)
        if not move.is_en_passant and target_piece != PIECE_NONE:
            if self.side_to_move == WHITE and target_piece in WHITE_PIECES:
                return False
            if self.side_to_move == BLACK and target_piece in BLACK_PIECES:
                return False

        captured_piece = move.captured
        if captured_piece == PIECE_NONE and not move.is_en_passant:
            captured_piece = target_piece
        if move.is_castle and moving_piece not in (WK, BK):
            return False

        cap_sq = -1
        ep_captured = PIECE_NONE
        if move.is_en_passant:
            if self.en_passant != to_sq:
                return False
            cap_sq = to_sq - 8 if self.side_to_move == WHITE else to_sq + 8
            ep_captured = BP if self.side_to_move == WHITE else WP
            if self.piece_on(cap_sq) != ep_captured:
                return False

        undo = UndoState(
            move=move,
            captured_piece=captured_piece,
            castling_rights=self.castling_rights,
            en_passant=self.en_passant,
            halfmove_clock=self.halfmove_clock,
            fullmove_number=self.fullmove_number,
        )
        self.history.append(undo)

        self.piece_bitboards[moving_piece] = clear_bit(self.piece_bitboards[moving_piece], from_sq)

        if move.is_en_passant:
            self.piece_bitboards[ep_captured] = clear_bit(self.piece_bitboards[ep_captured], cap_sq)
        elif captured_piece != PIECE_NONE:
            self.piece_bitboards[captured_piece] = clear_bit(self.piece_bitboards[captured_piece], to_sq)

        placed_piece = moving_piece
        if move.promotion != PIECE_NONE:
            placed_piece = move.promotion

        self.piece_bitboards[placed_piece] = set_bit(self.piece_bitboards[placed_piece], to_sq)

        if move.is_castle:
            self._move_rook_for_castle(to_sq)

        self._update_castling_rights(from_sq, to_sq, moving_piece, captured_piece)

        self.en_passant = None
        if move.is_double_push:
            self.en_passant = to_sq - 8 if self.side_to_move == WHITE else to_sq + 8

        if moving_piece in (WP, BP) or captured_piece != PIECE_NONE:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1

        if self.side_to_move == BLACK:
            self.fullmove_number += 1

        self.side_to_move = opposite(self.side_to_move)
        self._recompute_occupancies()
        return True

    def unmake_move(self) -> bool:
        if not self.history:
            return False

        undo = self.history.pop()
        move = undo.move

        self.side_to_move = opposite(self.side_to_move)

        from_sq = move.from_square
        to_sq = move.to_square

        if move.is_castle:
            self._unmove_rook_for_castle(to_sq)

        moved_piece = move.piece

        if move.promotion != PIECE_NONE:
            self.piece_bitboards[move.promotion] = clear_bit(self.piece_bitboards[move.promotion], to_sq)
            self.piece_bitboards[moved_piece] = set_bit(self.piece_bitboards[moved_piece], from_sq)
        else:
            self.piece_bitboards[moved_piece] = clear_bit(self.piece_bitboards[moved_piece], to_sq)
            self.piece_bitboards[moved_piece] = set_bit(self.piece_bitboards[moved_piece], from_sq)

        if move.is_en_passant:
            cap_sq = to_sq - 8 if self.side_to_move == WHITE else to_sq + 8
            ep_captured = BP if self.side_to_move == WHITE else WP
            self.piece_bitboards[ep_captured] = set_bit(self.piece_bitboards[ep_captured], cap_sq)
        elif undo.captured_piece != PIECE_NONE:
            self.piece_bitboards[undo.captured_piece] = set_bit(self.piece_bitboards[undo.captured_piece], to_sq)

        self.castling_rights = undo.castling_rights
        self.en_passant = undo.en_passant
        self.halfmove_clock = undo.halfmove_clock
        self.fullmove_number = undo.fullmove_number

        self._recompute_occupancies()
        return True

    def _move_rook_for_castle(self, king_to: int) -> None:
        if king_to == G1:
            self.piece_bitboards[WR] = clear_bit(self.piece_bitboards[WR], H1)
            self.piece_bitboards[WR] = set_bit(self.piece_bitboards[WR], F1)
        elif king_to == C1:
            self.piece_bitboards[WR] = clear_bit(self.piece_bitboards[WR], A1)
            self.piece_bitboards[WR] = set_bit(self.piece_bitboards[WR], D1)
        elif king_to == G8:
            self.piece_bitboards[BR] = clear_bit(self.piece_bitboards[BR], H8)
            self.piece_bitboards[BR] = set_bit(self.piece_bitboards[BR], F8)
        elif king_to == C8:
            self.piece_bitboards[BR] = clear_bit(self.piece_bitboards[BR], A8)
            self.piece_bitboards[BR] = set_bit(self.piece_bitboards[BR], D8)

    def _unmove_rook_for_castle(self, king_to: int) -> None:
        if king_to == G1:
            self.piece_bitboards[WR] = clear_bit(self.piece_bitboards[WR], F1)
            self.piece_bitboards[WR] = set_bit(self.piece_bitboards[WR], H1)
        elif king_to == C1:
            self.piece_bitboards[WR] = clear_bit(self.piece_bitboards[WR], D1)
            self.piece_bitboards[WR] = set_bit(self.piece_bitboards[WR], A1)
        elif king_to == G8:
            self.piece_bitboards[BR] = clear_bit(self.piece_bitboards[BR], F8)
            self.piece_bitboards[BR] = set_bit(self.piece_bitboards[BR], H8)
        elif king_to == C8:
            self.piece_bitboards[BR] = clear_bit(self.piece_bitboards[BR], D8)
            self.piece_bitboards[BR] = set_bit(self.piece_bitboards[BR], A8)

    def _update_castling_rights(
        self,
        from_sq: int,
        to_sq: int,
        moving_piece: int,
        captured_piece: int,
    ) -> None:
        if moving_piece == WK:
            self.castling_rights &= ~(CASTLE_WHITE_KING | CASTLE_WHITE_QUEEN)
        elif moving_piece == BK:
            self.castling_rights &= ~(CASTLE_BLACK_KING | CASTLE_BLACK_QUEEN)
        elif moving_piece == WR:
            if from_sq == H1:
                self.castling_rights &= ~CASTLE_WHITE_KING
            elif from_sq == A1:
                self.castling_rights &= ~CASTLE_WHITE_QUEEN
        elif moving_piece == BR:
            if from_sq == H8:
                self.castling_rights &= ~CASTLE_BLACK_KING
            elif from_sq == A8:
                self.castling_rights &= ~CASTLE_BLACK_QUEEN

        if captured_piece == WR:
            if to_sq == H1:
                self.castling_rights &= ~CASTLE_WHITE_KING
            elif to_sq == A1:
                self.castling_rights &= ~CASTLE_WHITE_QUEEN
        elif captured_piece == BR:
            if to_sq == H8:
                self.castling_rights &= ~CASTLE_BLACK_KING
            elif to_sq == A8:
                self.castling_rights &= ~CASTLE_BLACK_QUEEN

    def _recompute_occupancies(self) -> None:
        white_occ = 0
        black_occ = 0
        for p in WHITE_PIECES:
            white_occ |= self.piece_bitboards[p]
        for p in BLACK_PIECES:
            black_occ |= self.piece_bitboards[p]

        self.occupancies[WHITE] = white_occ
        self.occupancies[BLACK] = black_occ
        self.occupancies[BOTH] = white_occ | black_occ

    def debug_state(self) -> tuple:
        return (
            tuple(self.piece_bitboards),
            tuple(self.occupancies),
            self.side_to_move,
            self.castling_rights,
            self.en_passant,
            self.halfmove_clock,
            self.fullmove_number,
        )

    def to_fen(self) -> str:
        ranks: list[str] = []
        for r in range(7, -1, -1):
            empty = 0
            parts: list[str] = []
            for f in range(8):
                sq = r * 8 + f
                piece = self.piece_on(sq)
                if piece == PIECE_NONE:
                    empty += 1
                else:
                    if empty:
                        parts.append(str(empty))
                        empty = 0
                    parts.append(PIECE_SYMBOLS[piece])
            if empty:
                parts.append(str(empty))
            ranks.append("".join(parts))

        castling = ""
        if self.castling_rights & CASTLE_WHITE_KING:
            castling += "K"
        if self.castling_rights & CASTLE_WHITE_QUEEN:
            castling += "Q"
        if self.castling_rights & CASTLE_BLACK_KING:
            castling += "k"
        if self.castling_rights & CASTLE_BLACK_QUEEN:
            castling += "q"
        if not castling:
            castling = "-"

        ep = "-" if self.en_passant is None else square_name(self.en_passant)
        side = "w" if self.side_to_move == WHITE else "b"
        return (
            f"{'/'.join(ranks)} {side} {castling} {ep} "
            f"{self.halfmove_clock} {self.fullmove_number}"
        )

    def __str__(self) -> str:
        rows = []
        for r in range(7, -1, -1):
            row = []
            for f in range(8):
                sq = r * 8 + f
                piece = self.piece_on(sq)
                if piece == PIECE_NONE:
                    row.append(".")
                else:
                    row.append(PIECE_SYMBOLS[piece])
            rows.append(" ".join(row))
        ep = "-" if self.en_passant is None else square_name(self.en_passant)
        side = "w" if self.side_to_move == WHITE else "b"
        return "\n".join(rows) + f"\nside={side} castle={self.castling_rights} ep={ep}"
