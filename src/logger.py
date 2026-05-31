# =========================
# 戰鬥記錄器
# =========================
class BattleRecorder:
    def __init__(self):
        # 整場戰鬥紀錄
        self.turns = []

        # 目前正在記錄的 turn
        self.current_turn = None

        # 目前正在記錄的 tick
        self.current_tick = None

        # 目前正在記錄的 unit action
        self.current_unit = None

    def start_turn(self, turn):
        # 開啟一個新的 turn block
        self.current_turn = {
            "turn": turn,
            "ticks": []
        }

        self.turns.append(self.current_turn)

    def start_tick(self, tick):
        # 開啟一個新的 tick block
        self.current_tick = {
            "tick": tick,
            "unit_actions": []
        }

        self.current_turn["ticks"].append(self.current_tick)

    def start_unit(self, unit):
        # 開啟一個新的 unit action block
        self.current_unit = {
            "unit": unit.name,
            "team": unit.team,
            "role": unit.role,
            "hp_start": unit.body.hp,
            "ap_start": unit.body.ap,
            "state_start": unit.body.state(),
            "events": []
        }

        self.current_tick["unit_actions"].append(self.current_unit)

    def log(self, event_type, target=None, **data):
        # 把事件寫入目前 unit action block
        event = {
            "event": event_type,
            "target": target.name if target else None,
            "target_team": target.team if target else None,
            "data": data
        }

        self.current_unit["events"].append(event)