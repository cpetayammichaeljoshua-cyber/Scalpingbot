# Trading Signal Bot

## Overview

This is a streamlined Telegram signal processing bot that receives, parses, and forwards trading signals. The bot focuses specifically on Telegram functionality, processing incoming trading signals and forwarding them to designated chats or channels. It includes signal parsing capabilities, risk analysis, and formatted message forwarding without complex web interfaces or direct trading execution.

## User Preferences

- Preferred communication style: Simple, everyday language
- Focus: Telegram-only signal processing (no web interface)
- Functionality: Signal forwarding to bot and channel targets
- User: Michael Joshua Tayam
- Bot Type: Fully automated signal processing and forwarding
- Features: Professional formatting, auto-forwarding, statistics tracking

## System Architecture

### Core Components

The application follows a simplified architecture focused on Telegram signal processing:

- **Simple Signal Bot** (`simple_signal_bot.py`): Main bot that handles Telegram API communication and signal forwarding
- **Signal Parser** (`signal_parser.py`): Parses trading signals from text messages
- **Risk Manager** (`risk_manager.py`): Analyzes signals for risk assessment
- **Configuration** (`config.py`): Manages bot settings and API credentials
- **Database** (`database.py`): Optional data storage for signal history

### Signal Processing Flow

1. **Signal Reception**: Signals received via Telegram messages using HTTP API polling
2. **Parsing**: Text-based signals parsed using regex patterns for various formats
3. **Risk Analysis**: Basic risk assessment and signal validation
4. **Formatting**: Signals formatted with emojis and structured layout
5. **Forwarding**: Processed signals forwarded to target Telegram chats/channels
6. **Confirmation**: User receives confirmation of successful signal processing

### Data Storage

Uses SQLite database for persistent storage of:
- User profiles and settings
- Trading signals and execution history
- Portfolio data and performance metrics
- Risk management parameters

### Authentication & Security

- Telegram bot token-based authentication
- Binance API key/secret for exchange access
- Session-based security for web dashboard
- Environment variable configuration for sensitive data

### Frontend Architecture

- **Framework**: Bootstrap 5 with vanilla JavaScript
- **Real-time Updates**: Periodic AJAX refresh for dashboard data
- **Responsive Design**: Mobile-friendly interface
- **Interactive Elements**: Signal testing, portfolio monitoring, trade history

## External Dependencies

### Trading Exchange
- **Binance API**: Primary trading platform integration via CCXT library
- **Market Data**: Real-time price feeds and historical OHLCV data

### Communication Platforms
- **Telegram Bot API**: User interface and signal reception
- **Cornix Platform**: Signal forwarding and automation integration

### Technical Analysis
- **pandas**: Data manipulation and analysis
- **pandas_ta**: Technical indicators library (optional)
- **numpy**: Numerical computations

### Web Framework
- **Flask**: HTTP server for webhooks and dashboard
- **Bootstrap**: Frontend UI framework
- **Font Awesome**: Icon library

### Database
- **SQLite**: Local database storage via aiosqlite for async operations

### Configuration
- **Environment Variables**: Secure configuration management for API keys and settings
- **JSON Configuration**: Runtime settings and user preferences