"""H3 步數預設（docs/rules/H3.md〈步數〉）：三個範本（make_film／make_battle／make_studio）都呼叫這裡，規則只寫一次。

- 有聲音的人臉（說話或唱歌、全景以外，正臉／3/4／側臉都算）→ 14 步：DMAD 4 步牙齒糊成白帶、嘴型偏弱。
- 全身快動作與走路入鏡（鏡頭寫 "motion"）→ 14 步：4 步會暴色塊、拖殘影、多一條腿。
- 其他（全景、遠景、空景、無聲靜態鏡）→ DMAD 4 步（spec 的 "draft": true）。
該鏡自己寫了 "draft" 或 "h3_steps" 就照寫的，不套預設。
"""

WIDE = {"WIDE", "WS", "LS", "EWS", "ELS", "FULL", "全景", "遠景", "大遠景"}
MOTION = {"fast", "walk", "dance", "jump", "fight", "快動作", "走路", "舞蹈", "跳躍", "打鬥"}


def needs_14(voiced, dist=None, motion=None):
    """voiced：這鏡畫面裡的人有在說話或唱歌；dist：景別（CU／MCU／MS／WIDE…）；motion：動作類型。"""
    if motion and str(motion).lower() in MOTION:
        return True
    return bool(voiced) and str(dist or "").upper() not in WIDE and str(dist or "") not in WIDE


def draft_for(shot, voiced):
    """回傳 spec 的 draft（True＝DMAD 4 步、False＝14 步）。"""
    if "draft" in shot:
        return bool(shot["draft"])
    if shot.get("h3_steps"):
        return int(shot["h3_steps"]) == 4
    return not needs_14(voiced, shot.get("dist"), shot.get("motion"))


if __name__ == "__main__":
    assert draft_for({"dist": "CU"}, True) is False
    assert draft_for({"dist": "WIDE"}, True) is True
    assert draft_for({"dist": "WIDE", "motion": "walk"}, False) is False
    assert draft_for({"dist": "MCU"}, False) is True
    assert draft_for({}, True) is False
    assert draft_for({"draft": True, "dist": "CU"}, True) is True
    assert draft_for({"h3_steps": 14}, False) is False
    print("ok")
