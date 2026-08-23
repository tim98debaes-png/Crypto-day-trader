from pathlib import Path

path = Path('app.py')
s = path.read_text(encoding='utf-8')
old_equity = '''        if len(equity):\n            equity[i] = cash\n\n    result = calculate_metrics(\n'''
new_equity = '''        if len(equity):\n            if position == 0:\n                equity[i] = cash\n            else:\n                if position == 1:\n                    mark_price = close[i] * (1 - slip / 100)\n                    unrealized = (mark_price - entry) * quantity\n                else:\n                    mark_price = close[i] * (1 + slip / 100)\n                    unrealized = (entry - mark_price) * quantity\n\n                estimated_exit_fees = (\n                    entry * quantity\n                    + mark_price * quantity\n                ) * fee / 100\n\n                equity[i] = (\n                    cash\n                    + unrealized\n                    - estimated_exit_fees\n                )\n\n    # Force-close any position that is still open at the end of the\n    # test period. Leaving it unrealized makes final return and trade\n    # count depend on the arbitrary dataset boundary.\n    if position != 0 and len(data):\n        final_price = close[-1]\n\n        if position == 1:\n            execution_exit = final_price * (1 - slip / 100)\n            gross = (execution_exit - entry) * quantity\n        else:\n            execution_exit = final_price * (1 + slip / 100)\n            gross = (entry - execution_exit) * quantity\n\n        fees = (\n            entry * quantity\n            + execution_exit * quantity\n        ) * fee / 100\n\n        pnl = gross - fees\n        cash += pnl\n        pnls.append(float(pnl))\n        position = 0\n        equity[-1] = cash\n\n    result = calculate_metrics(\n'''
if old_equity not in s:
    raise SystemExit('Expected equity block not found; aborting.')
s = s.replace(old_equity, new_equity, 1)
path.write_text(s, encoding='utf-8')
