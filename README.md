# Video Gem

A video processing application that uses OpenRouter and ElevenLabs APIs.

## Setup

1. Install dependencies:
   ```bash
   poetry install
   ```

2. Create a `.env` file with your API keys:
   ```
   OPENROUTER_API_KEY=your_key_here
   ELEVENLABS_API_KEY=your_key_here
   ```

3. Run the application:
   ```bash
   poetry run python main.py
   ```

## Usage

Place your input video file in the project directory and update `VIDEO_FILE_PATH` in `main.py`.
