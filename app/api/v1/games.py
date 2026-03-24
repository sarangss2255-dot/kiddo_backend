"""Game endpoints."""
import uuid
import random
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import chess
import chess.pgn
from app.database import get_db, SessionLocal
from app.models.models import User, GameType, GameSession, UserRole, PvpMatch, PvpMatchStatus
from app.schemas import GameSessionCreate, GameSessionResponse, GameTypeResponse, PvpInviteResponse, PvpJoinResponse
from app.api.deps import get_current_user, get_current_kid_or_parent
from app.core.security import verify_token

router = APIRouter(prefix="/games", tags=["Games"])


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active:
            del self.active[user_id]

    async def send(self, user_id: str, message: dict):
        ws = self.active.get(user_id)
        if ws:
            await ws.send_json(message)


manager = ConnectionManager()
match_queue: List[str] = []
matches: Dict[str, Dict[str, Any]] = {}
invite_map: Dict[str, str] = {}


@router.get("/types", response_model=List[GameTypeResponse])
async def list_game_types(db: Session = Depends(get_db)):
    """List all available game types."""
    game_types = db.query(GameType).filter(GameType.is_active == True).all()
    return [GameTypeResponse.model_validate(gt) for gt in game_types]


def _level_for_user(user: User) -> int:
    points = user.points_balance or 0
    if points < 200:
        return 1
    if points < 500:
        return 2
    if points < 1000:
        return 3
    return 4


def _time_control_for_user(user: User) -> int:
    # kids: shorter time for younger (or lower points). 5/8/10 mins.
    level = _level_for_user(user)
    return 300 if level == 1 else 480 if level == 2 else 600


def _points_for_result(user: User, result: str) -> int:
    level = _level_for_user(user)
    if result == "win":
        return 20 + level * 10
    if result == "draw":
        return 5 + level * 5
    return 2


def _make_invite_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(alphabet) for _ in range(6))


def _is_kid_role(role: Any) -> bool:
    return role == UserRole.KID or role == UserRole.KID.value


def _finish_match_db(match_id: str, winner_id: Optional[str], result: str):
    db = SessionLocal()
    try:
        match = db.query(PvpMatch).filter(PvpMatch.id == match_id).first()
        if not match:
            return
        match.status = PvpMatchStatus.COMPLETED
        match.ended_at = datetime.utcnow()
        match.winner_id = winner_id

        # Award points
        white = db.query(User).filter(User.id == match.player_white_id).first()
        black = db.query(User).filter(User.id == match.player_black_id).first() if match.player_black_id else None

        if white:
            if winner_id == str(white.id):
                white.points_balance += _points_for_result(white, "win")
            elif winner_id is None:
                white.points_balance += _points_for_result(white, "draw")
            else:
                white.points_balance += _points_for_result(white, "loss")

        if black:
            if winner_id == str(black.id):
                black.points_balance += _points_for_result(black, "win")
            elif winner_id is None:
                black.points_balance += _points_for_result(black, "draw")
            else:
                black.points_balance += _points_for_result(black, "loss")

        db.commit()
    finally:
        db.close()


@router.post("/chess/pvp/invite", response_model=PvpInviteResponse)
async def create_pvp_invite(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.KID:
        raise HTTPException(status_code=403, detail="Only kids can play PVP")

    game_type = db.query(GameType).filter(GameType.name == "chess_pvp").first()
    if not game_type:
        game_type = GameType(name="chess_pvp", description="Chess PVP matches", points_reward_base=0, icon="♟️")
        db.add(game_type)
        db.flush()

    invite_code = _make_invite_code()
    match = PvpMatch(
        player_white_id=current_user.id,
        status=PvpMatchStatus.WAITING,
        invite_code=invite_code,
        time_control_seconds=_time_control_for_user(current_user),
        created_at=datetime.utcnow(),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    invite_map[invite_code] = str(match.id)
    matches[str(match.id)] = {
        "board": chess.Board(),
        "white": str(match.player_white_id),
        "black": None,
        "pgn": chess.pgn.Game(),
    }

    return PvpInviteResponse(
        match_id=match.id,
        invite_code=invite_code,
        time_control_seconds=match.time_control_seconds,
    )


@router.post("/chess/pvp/invite/{invite_code}/join", response_model=PvpJoinResponse)
async def join_pvp_invite(
    invite_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.KID:
        raise HTTPException(status_code=403, detail="Only kids can play PVP")

    match_id = invite_map.get(invite_code)
    if not match_id:
        raise HTTPException(status_code=404, detail="Invite not found")

    match = db.query(PvpMatch).filter(PvpMatch.id == match_id).first()
    if not match or match.status != PvpMatchStatus.WAITING:
        raise HTTPException(status_code=400, detail="Match not available")

    match.player_black_id = current_user.id
    match.status = PvpMatchStatus.ACTIVE
    match.started_at = datetime.utcnow()
    db.commit()
    db.refresh(match)

    mem_match = matches.get(str(match.id))
    if mem_match:
        mem_match["black"] = str(current_user.id)

    return PvpJoinResponse(
        match_id=match.id,
        invite_code=invite_code,
        status=match.status,
    )


# ============= Chess Puzzle =============
@router.get("/chess/puzzle")
async def get_chess_puzzle(
    difficulty: str = "medium",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a chess puzzle for the user to solve."""
    # Generate a chess puzzle based on difficulty
    # This is a simplified version - in production, you'd have a database of puzzles
    puzzles = {
        "easy": {
            "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
            "solution": "Qxf7#",
            "hint": "Look for a checkmate!",
            "points": 10
        },
        "medium": {
            "fen": "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
            "solution": "Qxf7#",
            "hint": "The queen can deliver checkmate",
            "points": 25
        },
        "hard": {
            "fen": "r2qkb1r/pp2pppp/2p2n2/3p4/3P1Bb1/4P1P1/PPP2P1P/RN1QKB1R w KQkq - 0 7",
            "solution": "Bxf6",
            "hint": "Win material with a tactical shot",
            "points": 50
        }
    }

    puzzle = puzzles.get(difficulty, puzzles["medium"])
    puzzle["difficulty"] = difficulty
    puzzle["game_type"] = "chess"

    return puzzle


@router.post("/chess/submit", response_model=GameSessionResponse)
async def submit_chess_solution(
    puzzle_id: str,
    solution: str,
    difficulty: str = "medium",
    time_seconds: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit a chess puzzle solution."""
    if current_user.role != UserRole.KID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only kids can play games"
        )

    # Get game type
    game_type = db.query(GameType).filter(GameType.name == "chess").first()
    if not game_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game type not found")

    # Simplified scoring - in production, validate the actual solution
    # For now, award points based on difficulty
    points_map = {"easy": 10, "medium": 25, "hard": 50}
    points_earned = points_map.get(difficulty, 10)

    # Create session
    session = GameSession(
        user_id=current_user.id,
        game_type_id=game_type.id,
        score=100,  # Correct solution
        points_earned=points_earned,
        difficulty=difficulty,
        duration_seconds=time_seconds
    )
    db.add(session)

    # Award points
    current_user.points_balance += points_earned

    db.commit()
    db.refresh(session)

    return GameSessionResponse.model_validate(session)


# ============= Math Quiz =============
@router.get("/math/question")
async def get_math_question(
    difficulty: str = "medium",
    age: int = 8,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a math question based on difficulty and age."""
    import random

    # Adjust difficulty based on age
    if age <= 7:
        difficulty = "easy"
        max_num = 10
        operations = ["+", "-"]
    elif age <= 10:
        difficulty = "medium"
        max_num = 50
        operations = ["+", "-", "*"]
    else:
        difficulty = "hard" if difficulty != "easy" else difficulty
        max_num = 100
        operations = ["+", "-", "*", "/"]

    operation = random.choice(operations)

    if operation == "+":
        a, b = random.randint(1, max_num), random.randint(1, max_num)
        answer = a + b
        question = f"{a} + {b} = ?"
    elif operation == "-":
        a, b = random.randint(1, max_num), random.randint(1, max_num)
        if a < b:
            a, b = b, a
        answer = a - b
        question = f"{a} - {b} = ?"
    elif operation == "*":
        a, b = random.randint(1, min(12, max_num)), random.randint(1, min(12, max_num))
        answer = a * b
        question = f"{a} × {b} = ?"
    else:  # Division
        b = random.randint(1, 12)
        answer = random.randint(1, 12)
        a = b * answer
        question = f"{a} ÷ {b} = ?"

    points_map = {"easy": 5, "medium": 10, "hard": 15}

    return {
        "question": question,
        "answer": answer,
        "difficulty": difficulty,
        "points": points_map.get(difficulty, 10),
        "game_type": "math"
    }


@router.post("/math/answer", response_model=GameSessionResponse)
async def submit_math_answer(
    correct: bool,
    difficulty: str = "medium",
    time_seconds: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit a math answer."""
    if current_user.role != UserRole.KID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only kids can play games"
        )

    game_type = db.query(GameType).filter(GameType.name == "math").first()
    if not game_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game type not found")

    points_map = {"easy": 5, "medium": 10, "hard": 15}
    points_earned = points_map.get(difficulty, 10) if correct else 0

    session = GameSession(
        user_id=current_user.id,
        game_type_id=game_type.id,
        score=100 if correct else 0,
        points_earned=points_earned,
        difficulty=difficulty,
        duration_seconds=time_seconds
    )
    db.add(session)

    if correct:
        current_user.points_balance += points_earned

    db.commit()
    db.refresh(session)

    return GameSessionResponse.model_validate(session)


# ============= Memory Game =============
@router.get("/memory/setup")
async def get_memory_setup(
    difficulty: str = "medium",
    theme: str = "animals",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get memory game card setup."""
    # Grid sizes
    grid_sizes = {
        "easy": (4, 4),    # 8 pairs
        "medium": (4, 6),  # 12 pairs
        "hard": (6, 6)     # 18 pairs
    }

    # Card themes
    themes = {
        "animals": ["🐶", "🐱", "🐭", "🐹", "🐰", "🦊", "🐻", "🐼", "🐨", "🐯", "🦁", "🐮", "🐷", "🐸", "🐵", "🦄", "🐝", "🦋"],
        "fruits": ["🍎", "🍐", "🍊", "🍋", "🍌", "🍉", "🍇", "🍓", "🫐", "🍑", "🍒", "🥝", "🍍", "🥭", "🍈", "🫒", "🥥", "🫑"],
        "shapes": ["⭐", "❤️", "🔷", "🔶", "⬛", "⚪", "🔺", "🟢", "🟣", "🟡", "🔻", "🟠", "💠", "⬜", "🟥", "🟦", "🌀", "💫"]
    }

    rows, cols = grid_sizes.get(difficulty, (4, 4))
    num_pairs = (rows * cols) // 2

    cards = themes.get(theme, themes["animals"])[:num_pairs]
    card_pairs = cards + cards  # Duplicate for matching

    import random
    random.shuffle(card_pairs)

    points_map = {"easy": 10, "medium": 20, "hard": 30}

    return {
        "grid": {"rows": rows, "cols": cols},
        "cards": card_pairs,
        "difficulty": difficulty,
        "theme": theme,
        "points_base": points_map.get(difficulty, 20),
        "game_type": "memory"
    }


@router.post("/memory/complete", response_model=GameSessionResponse)
async def complete_memory_game(
    moves: int,
    time_seconds: int,
    difficulty: str = "medium",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Complete a memory game and get points."""
    if current_user.role != UserRole.KID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only kids can play games"
        )

    game_type = db.query(GameType).filter(GameType.name == "memory").first()
    if not game_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game type not found")

    # Calculate points based on moves and difficulty
    # Fewer moves = more points
    base_points = {"easy": 10, "medium": 20, "hard": 30}.get(difficulty, 20)
    min_moves = {"easy": 8, "medium": 12, "hard": 18}.get(difficulty, 12)

    # Bonus for efficiency
    if moves <= min_moves * 1.5:
        points_earned = base_points + 5
    elif moves <= min_moves * 2:
        points_earned = base_points
    else:
        points_earned = max(5, base_points - 5)

    session = GameSession(
        user_id=current_user.id,
        game_type_id=game_type.id,
        score=moves,  # Lower is better
        points_earned=points_earned,
        difficulty=difficulty,
        duration_seconds=time_seconds
    )
    db.add(session)

    current_user.points_balance += points_earned

    db.commit()
    db.refresh(session)

    return GameSessionResponse.model_validate(session)


# ============= Word Games =============
@router.get("/words/puzzle")
async def get_word_puzzle(
    difficulty: str = "medium",
    age: int = 8,
    game_mode: str = "scramble",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a word game puzzle."""
    import random

    # Word lists by difficulty
    words = {
        "easy": ["cat", "dog", "sun", "hat", "run", "big", "red", "cup", "pen", "box"],
        "medium": ["apple", "beach", "cloud", "dream", "earth", "fresh", "grape", "happy", "juice", "lemon"],
        "hard": ["amazing", "balance", "captain", "dolphin", "elegant", "fantasy", "genuine", "harmony", "imagine", "journey"]
    }

    word_list = words.get(difficulty, words["medium"])
    word = random.choice(word_list)

    if game_mode == "scramble":
        # Scramble the word
        letters = list(word)
        random.shuffle(letters)
        scrambled = "".join(letters)
        return {
            "type": "scramble",
            "scrambled": scrambled,
            "hint": f"A {len(word)}-letter word",
            "answer": word,
            "difficulty": difficulty,
            "points": {"easy": 5, "medium": 10, "hard": 15}.get(difficulty, 10),
            "game_type": "words"
        }
    elif game_mode == "fill":
        # Fill in the blank
        blank_idx = random.randint(0, len(word) - 1)
        display = word[:blank_idx] + "_" + word[blank_idx + 1:]
        return {
            "type": "fill",
            "display": display,
            "missing_letter": word[blank_idx],
            "answer": word,
            "difficulty": difficulty,
            "points": {"easy": 3, "medium": 5, "hard": 8}.get(difficulty, 5),
            "game_type": "words"
        }

    return {"error": "Invalid game mode"}


@router.post("/words/answer", response_model=GameSessionResponse)
async def submit_word_answer(
    correct: bool,
    difficulty: str = "medium",
    game_mode: str = "scramble",
    time_seconds: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit a word game answer."""
    if current_user.role != UserRole.KID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only kids can play games"
        )

    game_type = db.query(GameType).filter(GameType.name == "words").first()
    if not game_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game type not found")

    points_map = {"easy": 5, "medium": 10, "hard": 15}
    points_earned = points_map.get(difficulty, 10) if correct else 0

    session = GameSession(
        user_id=current_user.id,
        game_type_id=game_type.id,
        score=100 if correct else 0,
        points_earned=points_earned,
        difficulty=difficulty,
        duration_seconds=time_seconds
    )
    db.add(session)

    if correct:
        current_user.points_balance += points_earned

    db.commit()
    db.refresh(session)

    return GameSessionResponse.model_validate(session)


@router.get("/history", response_model=List[GameSessionResponse])
async def get_game_history(
    game_type: str = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get game session history for the current user."""
    query = db.query(GameSession).filter(GameSession.user_id == current_user.id)

    if game_type:
        gt = db.query(GameType).filter(GameType.name == game_type).first()
        if gt:
            query = query.filter(GameSession.game_type_id == gt.id)

    sessions = query.order_by(GameSession.completed_at.desc()).limit(limit).all()
    return [GameSessionResponse.model_validate(s) for s in sessions]


@router.websocket("/chess/pvp/ws")
async def chess_pvp_ws(websocket: WebSocket, token: str):
    payload = verify_token(token)
    if not payload:
        await websocket.close(code=1008)
        return
    user_id = payload.get("sub")
    role = payload.get("role")
    if not _is_kid_role(role):
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "queue":
                if user_id not in match_queue:
                    match_queue.append(user_id)
                if len(match_queue) >= 2:
                    white = match_queue.pop(0)
                    black = match_queue.pop(0)
                    # Create match in DB
                    db = SessionLocal()
                    try:
                        white_user = db.query(User).filter(User.id == white).first()
                        black_user = db.query(User).filter(User.id == black).first()
                        match = PvpMatch(
                            player_white_id=white,
                            player_black_id=black,
                            status=PvpMatchStatus.ACTIVE,
                            time_control_seconds=_time_control_for_user(white_user) if white_user else 0,
                            started_at=datetime.utcnow(),
                        )
                        db.add(match)
                        db.commit()
                        db.refresh(match)
                        match_id = str(match.id)
                    finally:
                        db.close()

                    matches[match_id] = {
                        "board": chess.Board(),
                        "white": white,
                        "black": black,
                        "pgn": chess.pgn.Game(),
                    }
                    await manager.send(white, {"action": "match_found", "match_id": match_id, "color": "white"})
                    await manager.send(black, {"action": "match_found", "match_id": match_id, "color": "black"})

            elif action == "join":
                match_id = data.get("match_id")
                if match_id in matches:
                    match = matches[match_id]
                    if match.get("black") is None and match.get("white") != user_id:
                        match["black"] = user_id
                    await manager.send(user_id, {"action": "match_joined", "match_id": match_id})

            elif action == "move":
                match_id = data.get("match_id")
                uci = data.get("uci")
                san = data.get("san")
                match = matches.get(match_id)
                if not match:
                    continue
                board: chess.Board = match["board"]
                try:
                    if uci:
                        move = chess.Move.from_uci(uci)
                    elif san:
                        move = board.parse_san(san)
                    else:
                        continue
                    if move in board.legal_moves:
                        board.push(move)
                        await manager.send(match["white"], {"action": "move", "uci": uci, "san": san})
                        await manager.send(match["black"], {"action": "move", "uci": uci, "san": san})
                        if board.is_game_over():
                            result = board.result()
                            winner = None
                            if result == "1-0":
                                winner = match["white"]
                            elif result == "0-1":
                                winner = match["black"]
                            await manager.send(match["white"], {"action": "game_over", "result": result, "winner": winner})
                            await manager.send(match["black"], {"action": "game_over", "result": result, "winner": winner})
                            _finish_match_db(match_id, winner, result)
                            match["status"] = "completed"
                except Exception:
                    continue

            elif action == "resign":
                match_id = data.get("match_id")
                match = matches.get(match_id)
                if not match:
                    continue
                winner = match["black"] if match["white"] == user_id else match["white"]
                await manager.send(match["white"], {"action": "game_over", "result": "resign", "winner": winner})
                await manager.send(match["black"], {"action": "game_over", "result": "resign", "winner": winner})
                _finish_match_db(match_id, winner, "resign")
                match["status"] = "completed"

            elif action == "emoji":
                match_id = data.get("match_id")
                emoji = data.get("emoji")
                match = matches.get(match_id)
                if not match or not emoji:
                    continue
                other = match["black"] if match["white"] == user_id else match["white"]
                if other:
                    await manager.send(other, {"action": "emoji", "emoji": emoji, "from": user_id})

            elif action == "rematch_request":
                match_id = data.get("match_id")
                match = matches.get(match_id)
                if not match:
                    continue
                other = match["black"] if match["white"] == user_id else match["white"]
                if other:
                    await manager.send(other, {"action": "rematch_request", "from": user_id, "match_id": match_id})

            elif action == "rematch_accept":
                match_id = data.get("match_id")
                match = matches.get(match_id)
                if not match:
                    continue
                white = match["white"]
                black = match["black"]
                if not white or not black:
                    continue
                # Swap colors for rematch
                white, black = black, white
                # Create new DB match
                db = SessionLocal()
                try:
                    white_user = db.query(User).filter(User.id == white).first()
                    match_db = PvpMatch(
                        player_white_id=white,
                        player_black_id=black,
                        status=PvpMatchStatus.ACTIVE,
                        time_control_seconds=_time_control_for_user(white_user) if white_user else 0,
                        started_at=datetime.utcnow(),
                    )
                    db.add(match_db)
                    db.commit()
                    db.refresh(match_db)
                    new_id = str(match_db.id)
                finally:
                    db.close()

                matches[new_id] = {
                    "board": chess.Board(),
                    "white": white,
                    "black": black,
                    "pgn": chess.pgn.Game(),
                }
                await manager.send(white, {"action": "match_found", "match_id": new_id, "color": "white"})
                await manager.send(black, {"action": "match_found", "match_id": new_id, "color": "black"})

    except WebSocketDisconnect:
        manager.disconnect(user_id)
