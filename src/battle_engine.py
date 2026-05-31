from battle_manager import UnitManager

# =========================
# 戰鬥引擎
# =========================
class BattleEngine:
    def __init__(self, units, battle_map):
        # 保存參戰單位
        self.units = units

        # UnitManager 負責戰鬥流程
        self.unit_manager = UnitManager(self.units)

        # BattleMap 負責空間位置
        self.battle_map = battle_map

    def setup(self):
        # 分出 RED 與 BLUE 隊伍
        team1 = [u for u in self.units if u.team == "RED"]
        team2 = [u for u in self.units if u.team != "RED"]

        # 依次放置雙方隊伍
        team_total = [team1, team2]
        for u in team_total:
            self.place_team(u)

        # 放置完成後開始戰鬥
        self.battle_start()

    def place_team(self, team):
        # 根據隊伍位置自動放置單位
        for x, u in enumerate(team):

            # BLUE 放在地圖右上側
            if u.team == "BLUE":
                x = self.battle_map.length - (1 + x)
                y = self.battle_map.width - 1

            # RED 放在地圖左下側
            else:
                y = 0

            self.battle_map.place_unit(u, x, y)
            print(u.team, u.name, "has been placed in", self.battle_map.positions[u])

    def battle_start(self):
        # 設定戰鬥回合與每回合 tick 數
        truns = 10
        tick = 5

        # 啟動戰鬥
        self.unit_manager.run_turns(truns, tick)