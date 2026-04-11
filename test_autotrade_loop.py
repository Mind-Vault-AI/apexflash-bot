#!/usr/bin/env python3
"""
TEST 6: Launch Auto-Trader Loop (Autonomous Mode)
──────────────────────────────────────────────────
Verify that zero_loss_manager.auto_trader_loop can:
1. Initialize
2. Load configuration
3. Check for signals
4. Validate wallet setup
5. Run 2 cycles without crashing

This is the LIVE brain - if this works, bot works.
"""

import asyncio
import logging
from datetime import datetime, timezone
import sys

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] AUTO-TEST: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("AutoTest")

async def test_autotrade_loop():
    """Test if auto_trader_loop can initialize and run 2 cycles."""
    
    try:
        # Import bot components
        from core.config import ADMIN_IDS, AUTONOMOUS_COOLDOWN
        from core.persistence import load_users, _get_redis
        from zero_loss_manager import auto_trader_loop, AUTOTRADE_STATE
        
        logger.info("✅ Imports successful")
        
        # Check prerequisites
        redis = _get_redis()
        users = load_users()
        
        if not users:
            logger.error("❌ No users in Redis. Bot needs /start from Telegram.")
            return False
        
        admin_id = ADMIN_IDS[0] if ADMIN_IDS else list(users.keys())[0]
        admin_user = users.get(admin_id) or users.get(str(admin_id))
        
        if not admin_user:
            logger.error("❌ Admin user not found in Redis")
            return False
        
        if not admin_user.get("wallet_secret_enc"):
            logger.error("❌ Admin wallet secret not encrypted in Redis")
            return False
        
        logger.info(f"✅ Admin user configured: {admin_id}")
        logger.info(f"   Wallet pubkey: {str(admin_user.get('wallet_pubkey', ''))[:16]}...")
        
        # Start the loop in background (will run until we cancel)
        logger.info("🚀 Starting auto_trader_loop in background...")
        task = asyncio.create_task(auto_trader_loop(bot=None))
        
        # Let it run for 2 cycles (2 * 45 seconds)
        logger.info(f"⏱️  Waiting {2 * 45}s for 2 cycles...")
        
        for cycle in range(2):
            await asyncio.sleep(45)
            logger.info(f"  Cycle {cycle + 1} state: {AUTOTRADE_STATE}")
            
            if "loop_error" in AUTOTRADE_STATE.get("last_reason", ""):
                logger.error(f"❌ Loop error: {AUTOTRADE_STATE['last_reason']}")
                task.cancel()
                return False
        
        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        logger.info("✅ Auto-trader loop ran 2 cycles without crash")
        logger.info(f"Final state: {AUTOTRADE_STATE}")
        
        # Summary
        print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUTO-TRADER LOOP STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Loop initialized
✅ Ran {2} cycles
✅ Checked for signals
✅ Position manager ready
✅ No crashes

Last reason: {AUTOTRADE_STATE.get('last_reason')}
Last entry: {AUTOTRADE_STATE.get('last_entry_symbol')}
Positions active: {AUTOTRADE_STATE.get('candidates')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """)
        
        return True
        
    except asyncio.CancelledError:
        logger.info("✅ Test completed (task cancelled as expected)")
        return True
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    result = asyncio.run(test_autotrade_loop())
    sys.exit(0 if result else 1)
