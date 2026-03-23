"""
Execution Adapter
order_intentをmoomoo OpenAPIでペーパートレード発注する
"""

from moomoo import *


class MoomooExecutor:
    def __init__(self, host="127.0.0.1", port=11111):
        self.host = host
        self.port = port
        self._trd_ctx = None

    def connect(self):
        """moomoo OpenAPIに接続"""
        self._trd_ctx = OpenSecTradeContext(
            host=self.host,
            port=self.port,
            security_firm=SecurityFirm.FUTUJP,
            filter_trdmarket=TrdMarket.US,
        )
        return self

    def close(self):
        """接続を閉じる"""
        if self._trd_ctx:
            self._trd_ctx.close()
            self._trd_ctx = None

    def execute(self, intent: dict, dry_run: bool = True) -> dict:
        """
        order_intentを実行する

        Args:
            intent: strategy_engineが生成したorder_intent
            dry_run: Trueなら発注せず記録のみ

        Returns:
            実行結果のdict
        """
        result = {
            "event_id": intent["event_id"],
            "ticker": intent["ticker"],
            "side": intent["side"],
            "size_usd": intent["size_usd"],
            "dry_run": dry_run,
            "status": "skipped",
            "order_id": None,
            "error": None,
        }

        if dry_run:
            result["status"] = "dry_run_recorded"
            return result

        if not self._trd_ctx:
            result["error"] = "Not connected to moomoo"
            return result

        try:
            side = TrdSide.BUY if intent["side"] == "BUY" else TrdSide.SELL

            # 成行注文（ペーパートレード）
            ret, data = self._trd_ctx.place_order(
                price=0,
                qty=1,  # TODO: size_usdから株数を計算
                code=intent["ticker"],
                trd_side=side,
                order_type=OrderType.MARKET,
                trd_env=TrdEnv.SIMULATE,
            )

            if ret == 0:
                result["status"] = "submitted"
                result["order_id"] = str(data.iloc[0].get("order_id", "unknown"))
            else:
                result["status"] = "failed"
                result["error"] = str(data)

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result
