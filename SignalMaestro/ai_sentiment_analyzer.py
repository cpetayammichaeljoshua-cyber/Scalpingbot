#!/usr/bin/env python3
"""
Advanced AI Sentiment Analyzer - GPT-5 Powered
Uses OpenAI's GPT-5 model to analyze news sentiment, social media data, and market reports
Integrates with the Ultimate Trading Bot for enhanced trading signals
"""

import asyncio
import logging
import os
import json
import aiohttp
import feedparser
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import sqlite3
from pathlib import Path
import hashlib
import time
from collections import defaultdict, deque
import traceback

# OpenAI imports
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# BeautifulSoup for web scraping
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# Async throttling
try:
    from asyncio_throttle import Throttler
    THROTTLER_AVAILABLE = True
except ImportError:
    THROTTLER_AVAILABLE = False

@dataclass
class SentimentData:
    """Sentiment analysis result structure"""
    source: str
    content: str
    sentiment_score: float  # -1.0 (very negative) to 1.0 (very positive)
    confidence: float      # 0.0 to 1.0
    market_impact: float   # 0.0 to 1.0 - predicted market impact
    key_themes: List[str]
    relevance_score: float # 0.0 to 1.0 - relevance to crypto/trading
    timestamp: datetime
    symbol_mentions: List[str]
    news_category: str
    sentiment_label: str   # "very_negative", "negative", "neutral", "positive", "very_positive"

@dataclass
class MarketSentimentSummary:
    """Overall market sentiment summary"""
    overall_sentiment: float
    confidence: float
    trending_themes: List[str]
    symbol_sentiments: Dict[str, float]
    news_volume: int
    sentiment_momentum: float  # Rate of change
    fear_greed_index: float
    market_risk_level: str
    sentiment_label: str  # "very_negative", "negative", "neutral", "positive", "very_positive"
    timestamp: datetime

class AISentimentAnalyzer:
    """
    Advanced AI Sentiment Analyzer using GPT-5
    Analyzes news, social media, and market reports for trading insights
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Initialize OpenAI client
        self.openai_client = None
        if OPENAI_AVAILABLE:
            try:
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    self.openai_client = OpenAI(api_key=api_key)
                    self.logger.info("🤖 OpenAI GPT-5 client initialized successfully")
                else:
                    self.logger.warning("⚠️ OPENAI_API_KEY not found in environment")
            except Exception as e:
                self.logger.error(f"❌ OpenAI client initialization failed: {e}")

        # Sentiment analysis configuration
        self.gpt_model = "gpt-5"  # Latest model released August 7, 2025
        self.max_tokens_per_request = 4000
        self.sentiment_cache_ttl = 300  # 5 minutes cache
        
        # Rate limiting for API calls
        self.api_throttler = None
        if THROTTLER_AVAILABLE:
            self.api_throttler = Throttler(rate_limit=30, period=60)  # 30 calls per minute
        
        # Data sources configuration
        self.news_sources = [
            {
                "name": "CoinDesk",
                "rss_url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
                "weight": 0.8,
                "category": "crypto_news"
            },
            {
                "name": "CoinTelegraph", 
                "rss_url": "https://cointelegraph.com/rss",
                "weight": 0.7,
                "category": "crypto_news"
            },
            {
                "name": "CryptoNews",
                "rss_url": "https://cryptonews.com/rss/",
                "weight": 0.6,
                "category": "crypto_news"
            },
            {
                "name": "Decrypt",
                "rss_url": "https://decrypt.co/feed",
                "weight": 0.7,
                "category": "crypto_news"
            }
        ]
        
        # Database for caching and historical analysis
        self.db_path = "SignalMaestro/sentiment_analysis.db"
        self._initialize_database()
        
        # Sentiment cache
        self.sentiment_cache = {}
        self.cache_timestamps = {}
        
        # Market symbols to track
        self.tracked_symbols = [
            "BTC", "ETH", "BNB", "ADA", "SOL", "DOGE", "MATIC", "AVAX",
            "DOT", "LINK", "UNI", "ATOM", "ALGO", "XRP", "LTC", "BCH"
        ]
        
        # Initialize sentiment tracking
        self.sentiment_history = deque(maxlen=1000)
        self.symbol_sentiment_trends = defaultdict(lambda: deque(maxlen=100))
        
        self.logger.info("🧠 AI Sentiment Analyzer initialized with GPT-5")

    def _initialize_database(self):
        """Initialize sentiment analysis database"""
        try:
            Path("SignalMaestro").mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Sentiment data table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sentiment_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT UNIQUE NOT NULL,
                    sentiment_score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    market_impact REAL NOT NULL,
                    key_themes TEXT NOT NULL,
                    relevance_score REAL NOT NULL,
                    symbol_mentions TEXT NOT NULL,
                    news_category TEXT NOT NULL,
                    sentiment_label TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Market sentiment summaries table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_sentiment_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    overall_sentiment REAL NOT NULL,
                    confidence REAL NOT NULL,
                    trending_themes TEXT NOT NULL,
                    symbol_sentiments TEXT NOT NULL,
                    news_volume INTEGER NOT NULL,
                    sentiment_momentum REAL NOT NULL,
                    fear_greed_index REAL NOT NULL,
                    market_risk_level TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Performance tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sentiment_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_accuracy REAL NOT NULL,
                    market_correlation REAL NOT NULL,
                    signal_precision REAL NOT NULL,
                    total_analyses INTEGER NOT NULL,
                    successful_predictions INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()
            conn.close()
            self.logger.info("📊 Sentiment analysis database initialized")

        except Exception as e:
            self.logger.error(f"❌ Database initialization failed: {e}")

    async def analyze_market_sentiment(self, symbol: Optional[str] = None) -> MarketSentimentSummary:
        """
        Comprehensive market sentiment analysis using GPT-5
        
        Args:
            symbol: Optional specific symbol to focus analysis on
            
        Returns:
            MarketSentimentSummary with comprehensive sentiment data
        """
        try:
            self.logger.info(f"🔍 Starting market sentiment analysis for {symbol or 'general market'}")
            
            # Collect news data
            news_data = await self._collect_news_data()
            
            # Analyze sentiment for each news item
            sentiment_results = []
            for news_item in news_data:
                sentiment = await self._analyze_text_sentiment(
                    news_item['content'],
                    news_item['source'],
                    focus_symbol=symbol
                )
                if sentiment:
                    sentiment_results.append(sentiment)
            
            # Generate market summary
            market_summary = await self._generate_market_summary(sentiment_results, symbol)
            
            # Store in database
            await self._store_market_summary(market_summary)
            
            # Update trends
            self._update_sentiment_trends(market_summary)
            
            self.logger.info(f"✅ Market sentiment analysis completed: {market_summary.sentiment_label}")
            return market_summary
            
        except Exception as e:
            self.logger.error(f"❌ Market sentiment analysis failed: {e}")
            return self._create_fallback_summary()

    async def _collect_news_data(self) -> List[Dict[str, Any]]:
        """Collect news data from multiple sources"""
        news_data = []
        
        for source in self.news_sources:
            try:
                # Rate limiting
                if self.api_throttler:
                    async with self.api_throttler:
                        feed_data = await self._fetch_rss_feed(source)
                else:
                    feed_data = await self._fetch_rss_feed(source)
                
                news_data.extend(feed_data)
                
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to fetch from {source['name']}: {e}")
        
        # Sort by recency and limit
        news_data.sort(key=lambda x: x.get('published', datetime.min), reverse=True)
        return news_data[:50]  # Limit to most recent 50 items

    async def _fetch_rss_feed(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch and parse RSS feed data"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(source['rss_url']) as response:
                    if response.status == 200:
                        content = await response.text()
                        
                        # Parse RSS feed
                        feed = feedparser.parse(content)
                        
                        feed_data = []
                        for entry in feed.entries[:20]:  # Limit per source
                            try:
                                # Extract content
                                content_text = ""
                                if hasattr(entry, 'summary'):
                                    content_text = entry.summary
                                elif hasattr(entry, 'description'):
                                    content_text = entry.description
                                elif hasattr(entry, 'content'):
                                    content_text = entry.content[0].value if entry.content else ""
                                
                                # Clean HTML if present
                                if BS4_AVAILABLE and content_text:
                                    soup = BeautifulSoup(content_text, 'html.parser')
                                    content_text = soup.get_text(strip=True)
                                
                                # Parse publish date
                                published = datetime.now()
                                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                                    try:
                                        # Fix: entry.published_parsed is a time.struct_time
                                        pp = entry.published_parsed
                                        # Ensure all required fields are present and valid
                                        year = int(pp.tm_year) if hasattr(pp, 'tm_year') else datetime.now().year
                                        month = int(pp.tm_mon) if hasattr(pp, 'tm_mon') else datetime.now().month
                                        day = int(pp.tm_mday) if hasattr(pp, 'tm_mday') else datetime.now().day
                                        hour = int(pp.tm_hour) if hasattr(pp, 'tm_hour') else 0
                                        minute = int(pp.tm_min) if hasattr(pp, 'tm_min') else 0
                                        second = int(pp.tm_sec) if hasattr(pp, 'tm_sec') else 0
                                        
                                        # Basic validation to prevent "year out of range" or similar
                                        if year < 1970: year = datetime.now().year
                                        if not (1 <= month <= 12): month = 1
                                        if not (1 <= day <= 31): day = 1
                                        
                                        published = datetime(year, month, day, hour, minute, second)
                                    except Exception as dt_err:
                                        self.logger.debug(f"⚠️ Datetime conversion error: {dt_err}")
                                        published = datetime.now()
                                
                                feed_data.append({
                                    'title': getattr(entry, 'title', ''),
                                    'content': content_text,
                                    'link': getattr(entry, 'link', ''),
                                    'published': published,
                                    'source': source['name'],
                                    'weight': source['weight'],
                                    'category': source['category']
                                })
                                
                            except Exception as e:
                                self.logger.debug(f"⚠️ Error parsing entry: {e}")
                                continue
                        
                        return feed_data
                    else:
                        return []
                        
        except Exception as e:
            self.logger.warning(f"⚠️ RSS fetch failed for {source['name']}: {e}")
            return []

    async def _analyze_text_sentiment(self, text: str, source: str, focus_symbol: Optional[str] = None) -> Optional[SentimentData]:
        """Use GPT-5 to analyze text sentiment"""
        try:
            if not self.openai_client or not text.strip():
                return None
            
            # Check cache first
            text_hash = hashlib.md5(text.encode()).hexdigest()
            if text_hash in self.sentiment_cache:
                cache_time = self.cache_timestamps.get(text_hash, 0)
                if time.time() - cache_time < self.sentiment_cache_ttl:
                    return self.sentiment_cache[text_hash]
            
            # Prepare prompt for GPT-5
            symbols_text = ", ".join(self.tracked_symbols)
            focus_text = f" Pay special attention to {focus_symbol}." if focus_symbol else ""
            
            prompt = f"""
Analyze the following cryptocurrency/financial news text for market sentiment. Focus on these symbols: {symbols_text}.{focus_text}

Text to analyze:
"{text[:2000]}"

Provide a JSON response with the following structure:
{{
    "sentiment_score": float between -1.0 (very negative) and 1.0 (very positive),
    "confidence": float between 0.0 and 1.0,
    "market_impact": float between 0.0 and 1.0 (predicted market impact),
    "key_themes": array of up to 5 key themes/topics,
    "relevance_score": float between 0.0 and 1.0 (relevance to crypto/trading),
    "symbol_mentions": array of cryptocurrency symbols mentioned,
    "sentiment_label": one of ["very_negative", "negative", "neutral", "positive", "very_positive"],
    "reasoning": brief explanation of the sentiment analysis
}}

Focus on:
- Market moving events
- Regulatory news
- Technology developments
- Adoption and partnerships
- Market sentiment indicators
"""

            # Rate limiting
            if self.api_throttler:
                async with self.api_throttler:
                    response = await self._make_gpt5_request(prompt)
            else:
                response = await self._make_gpt5_request(prompt)
            
            if response:
                # Parse response and create SentimentData
                sentiment_data = SentimentData(
                    source=source,
                    content=text[:500],  # Store first 500 chars
                    sentiment_score=response.get('sentiment_score', 0.0),
                    confidence=response.get('confidence', 0.0),
                    market_impact=response.get('market_impact', 0.0),
                    key_themes=response.get('key_themes', []),
                    relevance_score=response.get('relevance_score', 0.0),
                    timestamp=datetime.now(),
                    symbol_mentions=response.get('symbol_mentions', []),
                    news_category='crypto_news',
                    sentiment_label=response.get('sentiment_label', 'neutral')
                )
                
                # Cache result
                self.sentiment_cache[text_hash] = sentiment_data
                self.cache_timestamps[text_hash] = time.time()
                
                # Store in database
                await self._store_sentiment_data(sentiment_data, text_hash)
                
                return sentiment_data
                
        except Exception as e:
            self.logger.error(f"❌ Sentiment analysis failed: {e}")
            return None

    async def _make_gpt5_request(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Make request to GPT-5 API"""
        try:
            if not self.openai_client:
                self.logger.warning("OpenAI client not available")
                return None
                
            response = self.openai_client.chat.completions.create(
                model=self.gpt_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert financial and cryptocurrency market analyst. Provide accurate, objective sentiment analysis based on news content. Always respond with valid JSON."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=self.max_tokens_per_request,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            self.logger.error(f"❌ GPT-5 request failed: {e}")
            return None

    async def _generate_market_summary(self, sentiment_results: List[SentimentData], focus_symbol: Optional[str] = None) -> MarketSentimentSummary:
        """Generate comprehensive market sentiment summary"""
        try:
            if not sentiment_results:
                return self._create_fallback_summary()
            
            # Calculate overall metrics
            sentiments = [s.sentiment_score for s in sentiment_results if s.relevance_score > 0.3]
            confidences = [s.confidence for s in sentiment_results if s.relevance_score > 0.3]
            market_impacts = [s.market_impact for s in sentiment_results if s.relevance_score > 0.3]
            
            if not sentiments:
                return self._create_fallback_summary()
            
            # Weight by relevance and market impact
            weighted_sentiment = sum(
                s.sentiment_score * s.relevance_score * s.market_impact 
                for s in sentiment_results if s.relevance_score > 0.3
            ) / sum(
                s.relevance_score * s.market_impact 
                for s in sentiment_results if s.relevance_score > 0.3
            ) if sentiment_results else 0.0
            
            overall_sentiment = max(-1.0, min(1.0, weighted_sentiment))
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            # Extract trending themes
            all_themes = []
            for s in sentiment_results:
                all_themes.extend(s.key_themes)
            
            theme_counts = defaultdict(int)
            for theme in all_themes:
                theme_counts[theme] += 1
            
            trending_themes = [theme for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:5]]
            
            # Calculate symbol-specific sentiments
            symbol_sentiments = {}
            for symbol in self.tracked_symbols:
                symbol_mentions = [s for s in sentiment_results if symbol in s.symbol_mentions]
                if symbol_mentions:
                    symbol_sentiment = sum(s.sentiment_score for s in symbol_mentions) / len(symbol_mentions)
                    symbol_sentiments[symbol] = symbol_sentiment
            
            # Calculate sentiment momentum (rate of change)
            sentiment_momentum = 0.0
            if len(self.sentiment_history) > 1:
                recent_avg = sum(h.overall_sentiment for h in list(self.sentiment_history)[-5:]) / min(5, len(self.sentiment_history))
                older_avg = sum(h.overall_sentiment for h in list(self.sentiment_history)[-10:-5]) / min(5, len(self.sentiment_history))
                sentiment_momentum = recent_avg - older_avg
            
            # Calculate fear & greed index (simplified)
            fear_greed_index = max(0.0, min(100.0, (overall_sentiment + 1.0) * 50))
            
            # Determine market risk level
            if overall_sentiment < -0.5:
                market_risk_level = "HIGH"
            elif overall_sentiment < -0.2:
                market_risk_level = "ELEVATED"
            elif overall_sentiment > 0.5:
                market_risk_level = "LOW"
            elif overall_sentiment > 0.2:
                market_risk_level = "MODERATE"
            else:
                market_risk_level = "NEUTRAL"
            
            # Determine sentiment label
            if overall_sentiment < -0.6:
                sentiment_label = "very_negative"
            elif overall_sentiment < -0.2:
                sentiment_label = "negative"
            elif overall_sentiment > 0.6:
                sentiment_label = "very_positive"
            elif overall_sentiment > 0.2:
                sentiment_label = "positive"
            else:
                sentiment_label = "neutral"
            
            return MarketSentimentSummary(
                overall_sentiment=overall_sentiment,
                confidence=confidence,
                trending_themes=trending_themes,
                symbol_sentiments=symbol_sentiments,
                news_volume=len(sentiment_results),
                sentiment_momentum=sentiment_momentum,
                fear_greed_index=fear_greed_index,
                market_risk_level=market_risk_level,
                sentiment_label=sentiment_label,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"❌ Market summary generation failed: {e}")
            return self._create_fallback_summary()

    def get_symbol_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get sentiment data for specific symbol"""
        try:
            if symbol in self.symbol_sentiment_trends:
                recent_sentiments = list(self.symbol_sentiment_trends[symbol])
                if recent_sentiments:
                    current_sentiment = recent_sentiments[-1]
                    trend = "neutral"
                    
                    if len(recent_sentiments) >= 3:
                        recent_avg = sum(recent_sentiments[-3:]) / 3
                        older_avg = sum(recent_sentiments[-6:-3]) / 3 if len(recent_sentiments) >= 6 else recent_avg
                        
                        if recent_avg > older_avg + 0.1:
                            trend = "improving"
                        elif recent_avg < older_avg - 0.1:
                            trend = "declining"
                    
                    return {
                        'symbol': symbol,
                        'current_sentiment': current_sentiment,
                        'trend': trend,
                        'data_points': len(recent_sentiments),
                        'last_updated': datetime.now().isoformat()
                    }
            
            return {
                'symbol': symbol,
                'current_sentiment': 0.0,
                'trend': 'neutral',
                'data_points': 0,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"❌ Symbol sentiment retrieval failed: {e}")
            return {'symbol': symbol, 'current_sentiment': 0.0, 'trend': 'neutral', 'data_points': 0}

    async def _store_sentiment_data(self, sentiment_data: SentimentData, content_hash: str):
        """Store sentiment data in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO sentiment_data (
                    source, content, content_hash, sentiment_score, confidence,
                    market_impact, key_themes, relevance_score, symbol_mentions,
                    news_category, sentiment_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sentiment_data.source,
                sentiment_data.content,
                content_hash,
                sentiment_data.sentiment_score,
                sentiment_data.confidence,
                sentiment_data.market_impact,
                json.dumps(sentiment_data.key_themes),
                sentiment_data.relevance_score,
                json.dumps(sentiment_data.symbol_mentions),
                sentiment_data.news_category,
                sentiment_data.sentiment_label
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"❌ Sentiment data storage failed: {e}")

    async def _store_market_summary(self, summary: MarketSentimentSummary):
        """Store market sentiment summary in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO market_sentiment_summaries (
                    overall_sentiment, confidence, trending_themes, symbol_sentiments,
                    news_volume, sentiment_momentum, fear_greed_index, market_risk_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                summary.overall_sentiment,
                summary.confidence,
                json.dumps(summary.trending_themes),
                json.dumps(summary.symbol_sentiments),
                summary.news_volume,
                summary.sentiment_momentum,
                summary.fear_greed_index,
                summary.market_risk_level
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"❌ Market summary storage failed: {e}")

    def _update_sentiment_trends(self, summary: MarketSentimentSummary):
        """Update sentiment trend tracking"""
        try:
            # Add to overall history
            self.sentiment_history.append(summary)
            
            # Update symbol-specific trends
            for symbol, sentiment in summary.symbol_sentiments.items():
                self.symbol_sentiment_trends[symbol].append(sentiment)
                
        except Exception as e:
            self.logger.error(f"❌ Sentiment trend update failed: {e}")

    def _create_fallback_summary(self) -> MarketSentimentSummary:
        """Create fallback summary when analysis fails"""
        return MarketSentimentSummary(
            overall_sentiment=0.0,
            confidence=0.0,
            trending_themes=[],
            symbol_sentiments={},
            news_volume=0,
            sentiment_momentum=0.0,
            fear_greed_index=50.0,
            market_risk_level="UNKNOWN",
            sentiment_label="neutral",
            timestamp=datetime.now()
        )

    def get_sentiment_insights(self) -> Dict[str, Any]:
        """Get comprehensive sentiment insights for trading decisions"""
        try:
            latest_summary = self.sentiment_history[-1] if self.sentiment_history else self._create_fallback_summary()
            
            # Calculate sentiment strength
            sentiment_strength = abs(latest_summary.overall_sentiment)
            
            # Determine market bias
            if latest_summary.overall_sentiment > 0.3:
                market_bias = "bullish"
            elif latest_summary.overall_sentiment < -0.3:
                market_bias = "bearish"
            else:
                market_bias = "neutral"
            
            # Calculate sentiment velocity
            sentiment_velocity = 0.0
            if len(self.sentiment_history) >= 2:
                sentiment_velocity = self.sentiment_history[-1].overall_sentiment - self.sentiment_history[-2].overall_sentiment
            
            return {
                'overall_sentiment': latest_summary.overall_sentiment,
                'sentiment_strength': sentiment_strength,
                'market_bias': market_bias,
                'sentiment_velocity': sentiment_velocity,
                'confidence': latest_summary.confidence,
                'fear_greed_index': latest_summary.fear_greed_index,
                'market_risk_level': latest_summary.market_risk_level,
                'trending_themes': latest_summary.trending_themes,
                'news_volume': latest_summary.news_volume,
                'last_updated': latest_summary.timestamp.isoformat(),
                'signal_recommendation': self._get_trading_recommendation(latest_summary)
            }
            
        except Exception as e:
            self.logger.error(f"❌ Sentiment insights generation failed: {e}")
            return {
                'overall_sentiment': 0.0,
                'sentiment_strength': 0.0,
                'market_bias': 'neutral',
                'sentiment_velocity': 0.0,
                'confidence': 0.0,
                'signal_recommendation': 'hold'
            }

    def _get_trading_recommendation(self, summary: MarketSentimentSummary) -> str:
        """Generate trading recommendation based on sentiment"""
        try:
            sentiment = summary.overall_sentiment
            confidence = summary.confidence
            risk_level = summary.market_risk_level
            
            # High confidence recommendations
            if confidence > 0.7:
                if sentiment > 0.5 and risk_level in ["LOW", "MODERATE"]:
                    return "strong_buy"
                elif sentiment < -0.5 and risk_level in ["HIGH", "ELEVATED"]:
                    return "strong_sell"
                elif sentiment > 0.2:
                    return "buy"
                elif sentiment < -0.2:
                    return "sell"
            
            # Medium confidence recommendations
            elif confidence > 0.4:
                if sentiment > 0.3:
                    return "weak_buy"
                elif sentiment < -0.3:
                    return "weak_sell"
            
            return "hold"
            
        except Exception as e:
            self.logger.error(f"❌ Trading recommendation failed: {e}")
            return "hold"


# Global instance for easy access
_sentiment_analyzer = None

def get_sentiment_analyzer() -> AISentimentAnalyzer:
    """Get global sentiment analyzer instance"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        _sentiment_analyzer = AISentimentAnalyzer()
    return _sentiment_analyzer


# Example usage for testing
async def main():
    """Test the sentiment analyzer"""
    analyzer = get_sentiment_analyzer()
    
    # Test market sentiment analysis
    print("🔍 Testing market sentiment analysis...")
    market_sentiment = await analyzer.analyze_market_sentiment()
    print(f"Market Sentiment: {market_sentiment.overall_sentiment:.2f}")
    print(f"Confidence: {market_sentiment.confidence:.2f}")
    print(f"Risk Level: {market_sentiment.market_risk_level}")
    
    # Test insights
    insights = analyzer.get_sentiment_insights()
    print(f"Trading Recommendation: {insights['signal_recommendation']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())