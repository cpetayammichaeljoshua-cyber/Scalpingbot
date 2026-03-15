
#!/usr/bin/env python3
"""
Display all available bot commands
Shows comprehensive list of FXSUSDT bot + Freqtrade integration commands
"""

from freqtrade_telegram_commands import FreqtradeTelegramCommands

class DummyBot:
    """Dummy bot instance for command listing"""
    pass

def show_all_commands():
    """Display all available commands"""
    
    # Create dummy bot and Freqtrade commands instance
    dummy_bot = DummyBot()
    freqtrade_cmds = FreqtradeTelegramCommands(dummy_bot)
    
    print("=" * 80)
    print("🤖 FXSUSDT.P BOT - COMPLETE COMMAND REFERENCE")
    print("=" * 80)
    print()
    
    print("📊 FREQTRADE CORE BOT CONTROL COMMANDS:")
    print("-" * 80)
    bot_control = [
        ('/stop', 'Stop the trading bot'),
        ('/reload_config', 'Reload bot configuration'),
        ('/show_config', 'Show current bot configuration'),
    ]
    for cmd, desc in bot_control:
        print(f"  {cmd:30} - {desc}")
    print()
    
    print("💰 FREQTRADE PROFIT & PERFORMANCE COMMANDS:")
    print("-" * 80)
    profit_cmds = [
        ('/profit [days]', 'Show profit summary'),
        ('/performance', 'Show performance by trading pair'),
        ('/daily [days]', 'Show daily profit breakdown'),
        ('/weekly', 'Show weekly profit summary'),
        ('/monthly', 'Show monthly profit summary'),
    ]
    for cmd, desc in profit_cmds:
        print(f"  {cmd:30} - {desc}")
    print()
    
    print("📈 FREQTRADE TRADE MANAGEMENT COMMANDS:")
    print("-" * 80)
    trade_cmds = [
        ('/count', 'Show trade count statistics'),
        ('/forcebuy <pair> [rate]', 'Force buy a trading pair'),
        ('/forcesell <id|all>', 'Force sell/exit trade(s)'),
        ('/delete <trade_id>', 'Delete trade from database'),
        ('/trades [limit]', 'Show recent trades'),
    ]
    for cmd, desc in trade_cmds:
        print(f"  {cmd:30} - {desc}")
    print()
    
    print("🎯 FREQTRADE WHITELIST/BLACKLIST COMMANDS:")
    print("-" * 80)
    list_cmds = [
        ('/whitelist', 'Show trading pairs whitelist'),
        ('/blacklist [pair]', 'Show or add to blacklist'),
        ('/locks', 'Show current trade locks'),
        ('/unlock <pair|all>', 'Unlock trading pair(s)'),
    ]
    for cmd, desc in list_cmds:
        print(f"  {cmd:30} - {desc}")
    print()
    
    print("⚡ FREQTRADE STRATEGY COMMANDS:")
    print("-" * 80)
    strategy_cmds = [
        ('/edge', 'Show edge positioning information'),
        ('/stopbuy', 'Stop buying new trades (keep selling)'),
    ]
    for cmd, desc in strategy_cmds:
        print(f"  {cmd:30} - {desc}")
    print()
    
    print("🚀 FXSUSDT BOT NATIVE COMMANDS:")
    print("-" * 80)
    native_cmds = [
        ('/start', 'Initialize bot'),
        ('/help', 'Show help message'),
        ('/status', 'Bot status and uptime'),
        ('/price', 'Current FXSUSDT.P price'),
        ('/balance', 'Account balance information'),
        ('/position', 'Current open positions'),
        ('/scan', 'Manual market scan'),
        ('/settings', 'Display bot settings'),
        ('/market [symbol]', 'Market overview'),
        ('/stats', 'Bot statistics'),
        ('/leverage [sym] [amt]', 'Set leverage'),
        ('/risk [acct] [%]', 'Calculate risk per trade'),
        ('/signal <dir> <entry> <sl> <tp>', 'Manual signal (admin)'),
        ('/history', 'Recent trade history'),
        ('/alerts', 'Manage price alerts'),
        ('/admin', 'Admin panel'),
        ('/futures', 'Futures contract info'),
        ('/contract', 'Contract specifications'),
        ('/funding', 'Funding rate'),
        ('/oi', 'Open interest'),
        ('/volume', 'Volume analysis'),
        ('/sentiment', 'Market sentiment'),
        ('/news', 'Market news'),
        ('/watchlist', 'Manage watchlist'),
        ('/backtest [days] [tf]', 'Run backtest'),
        ('/optimize', 'Optimize strategy'),
        ('/dynamic_sltp LONG/SHORT', 'Smart SL/TP levels'),
        ('/dashboard', 'Market dashboard'),
    ]
    for cmd, desc in native_cmds:
        print(f"  {cmd:30} - {desc}")
    print()
    
    print("=" * 80)
    print(f"✅ TOTAL COMMANDS AVAILABLE: {len(bot_control) + len(profit_cmds) + len(trade_cmds) + len(list_cmds) + len(strategy_cmds) + len(native_cmds)}")
    print("=" * 80)
    print()
    print("💡 USAGE EXAMPLES:")
    print("  /profit 7              - Show profit for last 7 days")
    print("  /forcebuy FXS/USDT     - Force buy FXSUSDT pair")
    print("  /leverage FXSUSDT 10   - Set 10x leverage")
    print("  /backtest 30 1h        - Backtest 30 days on 1h timeframe")
    print("  /dynamic_sltp LONG     - Get smart SL/TP for long position")
    print()

if __name__ == "__main__":
    show_all_commands()
