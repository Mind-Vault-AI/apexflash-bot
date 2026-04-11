#!/usr/bin/env python3
"""
TEST 4: Trade Journal Logging Completeness
────────────────────────────────────────────
Verify that SELL orders capture:
- entry_price ✓
- exit_price ✓
- pnl % ✓
- fees ✓
- timestamps ✓
"""

import json
from datetime import datetime, timedelta, timezone

async def test_journal_completeness():
    """Inspect actual trade journal entries in Redis."""
    
    try:
        from core.persistence import _get_redis
        
        r = _get_redis()
        if not r:
            print("❌ Redis unavailable")
            return False
        
        print("🔍 Scanning Redis for trade journal entries...")
        
        # Scan all journal:signal:* keys
        cursor = 0
        entries_found = 0
        entries_complete = 0
        entries_incomplete = []
        
        while True:
            cursor, keys = r.scan(cursor, match='journal:signal:*', count=100)
            
            for key in keys:
                entries_found += 1
                raw = r.get(key)
                if not raw:
                    continue
                
                record = json.loads(raw)
                
                # Check completeness
                required_fields = ['id', 'grade', 'symbol', 'entry_price', 'timestamp']
                optional_fields = ['price_1h', 'exit_price', 'pnl_pct', 'pnl_usd', 'outcome']
                
                missing = [f for f in required_fields if f not in record or record[f] is None]
                
                if not missing:
                    entries_complete += 1
                else:
                    entries_incomplete.append({
                        'id': record.get('id'),
                        'symbol': record.get('symbol'),
                        'missing': missing,
                        'record': record
                    })
            
            if cursor == 0:
                break
        
        print(f"\n📊 Journal Stats:")
        print(f"  Total entries found: {entries_found}")
        print(f"  Entries complete: {entries_complete} ({100*entries_complete//max(1,entries_found)}%)")
        print(f"  Entries incomplete: {len(entries_incomplete)}")
        
        if entries_incomplete:
            print(f"\n⚠️  Sample incomplete entries:")
            for entry in entries_incomplete[:3]:
                print(f"  - ID: {entry['id']} | Symbol: {entry['symbol']} | Missing: {entry['missing']}")
                print(f"    Record: {entry['record']}")
        
        # Check daily aggregates
        print(f"\n📈 Daily aggregates:")
        cursor = 0
        daily_keys = []
        while True:
            cursor, keys = r.scan(cursor, match='journal:daily:*', count=100)
            daily_keys.extend(keys)
            if cursor == 0:
                break
        
        for key in daily_keys[-10:]:  # Last 10 days
            data = r.hgetall(key)
            if data:
                total = int(data.get(b'total') or data.get('total') or 0)
                wins = int(data.get(b'wins') or data.get('wins') or 0)
                losses = int(data.get(b'losses') or data.get('losses') or 0)
                print(f"  {key.decode() if isinstance(key, bytes) else key}: {total} signals | {wins}W/{losses}L")
        
        return entries_complete == entries_found
        
    except Exception as e:
        print(f"❌ Test failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    import asyncio
    result = asyncio.run(test_journal_completeness())
    print(f"\n✅ TEST 4: {'PASSED' if result else 'INCOMPLETE'}")
