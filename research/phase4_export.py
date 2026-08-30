"""Export and diagnose an executed BacktestResult without changing execution."""
from __future__ import annotations
import json
from pathlib import Path
from .phase4_diagnosis import diagnose

def export_result(result, output: str|Path):
    out=Path(output); out.mkdir(parents=True,exist_ok=True)
    trades=list(result.trades)
    (out/'trades.json').write_text(json.dumps(trades,indent=2,default=str)+'\n',encoding='utf-8')
    diagnosis=diagnose(trades)
    (out/'diagnosis.json').write_text(json.dumps(diagnosis,indent=2,default=str)+'\n',encoding='utf-8')
    (out/'equity_curve.json').write_text(json.dumps(result.equity_curve,indent=2,default=str)+'\n',encoding='utf-8')
    return diagnosis
