# Vantage Chess

Vantage Chess is a Python/Pygame desktop chess application ported and extended from an original HTML/JavaScript chess project. The application supports single-player games against an adjustable AI opponent, local two-player hot-seat play, and online multiplayer through a simple room-code relay system.

The project was developed as an HSC Software Engineering major project and demonstrates practical software engineering concepts including game logic, legal move validation, AI search, UI design, networking, threading, testing, documentation and project management.

## Features

- Full playable chess board with legal move enforcement
- Standard chess rules including check, checkmate and stalemate
- Special move support for castling, en passant and pawn promotion
- AI opponent with multiple difficulty levels
- Local two-player mode on one device
- Online multiplayer using room codes
- Move highlighting for easier user interaction
- Check highlighting and game-over overlay
- Move history panel using chess notation
- Captured-piece display
- Resizable Pygame window and fullscreen support
- Defensive error handling for network and input issues

## Project Background

The original version of Vantage Chess was built as an HTML/JavaScript browser application. This version re-engineers the project into a standalone Python/Pygame desktop application.

Major changes include:

- Rebuilding the full interface in Pygame
- Reworking browser-based interaction into desktop event handling
- Adding local hot-seat multiplayer
- Rebuilding online multiplayer using a lightweight HTTPS relay
- Moving network polling into background threads
- Improving rule correctness through testing and bug fixing
- Adding formal documentation, test records and design diagrams

## Technologies Used

| Technology | Purpose |
|---|---|
| Python | Main programming language |
| Pygame | Window, rendering, input and game loop |
| Git/GitHub | Version control and project backup |
| JSON relay service | Online multiplayer state synchronisation |
| Sphinx/Doxygen style documentation | Developer documentation |
| pytest/unittest | Testing engine and special move behaviour |

## Requirements

Before running the project, make sure Python is installed.

Recommended:

- Python 3.12 or later
- Pygame 2.6.1 or later
- Visual Studio Code or another Python IDE

Install Pygame using:

```bash
pip install pygame
```

## How to Run

Clone the repository:

```bash
git clone https://github.com/your-username/vantage-chess.git
cd vantage-chess
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python src/vantage_chess.py
```

If the project uses a single main file outside the `src` folder, run:

```bash
python vantage_chess.py
```

## How to Play

1. Launch the application.
2. Choose a game mode:
   - Play vs AI
   - Local 2 Player
   - Online Multiplayer
3. Select a side and difficulty if playing against the AI.
4. Click a piece to view its legal moves.
5. Click a highlighted square to move.
6. Use the sidebar to view move history, captured pieces and game status.
7. Press `F11` to toggle fullscreen.
8. Use the resign or new game button when needed.

## Game Modes

### Play vs AI

The user plays against a computer-controlled opponent. The AI uses minimax search with alpha-beta pruning and a board evaluation function based on material value and positional bonuses.

Difficulty levels adjust the depth and quality of the AI search.

### Local 2 Player

Two players share the same computer and take turns using the same mouse and screen. This mode works completely offline.

### Online Multiplayer

One player hosts a game and receives a room code. The second player joins using that code. The game state is synchronised through a lightweight relay so the project does not require a dedicated backend server.

## AI Overview

The AI system is based on:

- Legal move generation
- Board evaluation
- Material values
- Piece-square tables
- Minimax search
- Alpha-beta pruning
- Move ordering for improved efficiency

The AI only selects from legal moves and does not access hidden information.

## Project Structure

A typical folder structure is shown below:

```text
Vantage-Chess/
  README.md
  TESTING.md
  requirements.txt
  src/
    vantage_chess.py
    assets/
  tests/
    test_engine.py
    test_special_moves.py
    test_ai.py
    test_serialisation.py
  docs/
    source/
    build/html/
  documentation/
    Vantage_Chess_Report.docx
  presentation/
    Vantage_Chess_Presentation.pptx
```

## Testing

Testing focused on both normal gameplay and chess-rule edge cases.

Areas tested include:

- Legal move generation
- Check detection
- Checkmate and stalemate detection
- Castling restrictions
- En passant timing
- Pawn promotion
- AI move selection
- Local two-player turns
- Online room hosting and joining
- Network polling responsiveness
- Window resizing and fullscreen behaviour

Known defects found during testing, such as castling through check and en passant capture errors, were fixed and retested.

Run tests with:

```bash
pytest
```

or, if using unittest:

```bash
python -m unittest discover tests
```

## Security and Reliability

The project applies defensive programming strategies including:

- Input validation for room codes and user actions
- Legal move filtering before applying moves
- Graceful error handling for failed network requests
- Background-thread networking to reduce UI freezing
- Thread-safe callback queue for network results
- No user accounts, passwords or personal data collection

Online mode only shares board state and room data required for the chess match.

## Documentation

The project includes software engineering documentation covering:

- Source acknowledgement
- Methodology justification
- Requirements traceability
- Gantt chart
- UML class diagram
- Flowchart
- Risk register
- Test plan
- Logbook
- User manual
- Future improvements

## Future Improvements

Possible future improvements include:

- Add underpromotion options
- Save completed games as PGN files
- Add stronger AI through iterative deepening
- Add accessibility themes
- Improve online multiplayer latency
- Package the project as a Windows/macOS executable
- Add a replay and game-review system

## Acknowledgements

This Python/Pygame version is based on the developer's earlier original HTML/JavaScript Vantage Chess project. The desktop version was redesigned and extended to remove browser dependency and add new features suitable for a standalone app.

External resources used:

- Python documentation
- Pygame documentation
- GitHub for version control
- JSON relay service for online multiplayer state synchronisation

## Licence

This project is for educational use. Add a licence file if the repository is made public.
