# =========================
# 戰場空間系統
# =========================
from logger import BattleRecorder

class BattleMap:
    def __init__(self, length, width):
        # map 寬度與長度
        self.width = width
        self.length = length

        # positions 用 unit object 當 key，避免同名單位互相覆蓋
        self.positions = {}

    def is_inside(self, x, y):
        # 檢查座標是否在地圖範圍內
        return 0 <= x < self.length and 0 <= y < self.width

    def is_occupied(self, x, y):
        # 檢查某個座標是否已經被其他 unit 佔用
        return (x, y) in self.positions.values()

    def moving(self, attacker, target):
        # 取得 attacker 和 target 目前位置
        ux, uy = self.positions[attacker]
        tx, ty = self.positions[target]

        # 使用 Chebyshev distance，適合八方向移動
        def dist(x, y):
            return max(abs(tx - x), abs(ty - y))

        # 當前距離
        current_dist = dist(ux, uy)

        # 所有被佔用的位置
        occupied = set(self.positions.values())

        # 產生周圍 8 格候選位置，並過濾：
        # 1. 原地
        # 2. 出界
        # 3. 已被佔用
        # 4. 不能縮短距離的位置
        candidates = [
            (x, y)
            for dx in [-1, 0, 1]
            for dy in [-1, 0, 1]
            if not (dx == 0 and dy == 0)
            for x, y in [(ux + dx, uy + dy)]
            if self.is_inside(x, y)
            if (x, y) not in occupied
            if dist(x, y) < current_dist
        ]

        # 如果沒有任何合法且能縮短距離的位置，移動失敗
        if not candidates:
            print(f"{attacker.team}:{attacker.name} cannot move closer")
            return False

        # 選出距離 target 最近的候選位置
        new_x, new_y = min(candidates, key=lambda pos: dist(*pos))

        # 記錄 MOVE 事件
        BattleRecorder.log(
            "MOVE",
            target=target,
            old_pos=(ux, uy),
            new_pos=(new_x, new_y)
        )

        # 更新 attacker 位置
        self.positions[attacker] = (new_x, new_y)

        print(
            f"{attacker.team}:{attacker.name} moved from {(ux, uy)} "
            f"to {(new_x, new_y)}, distance {current_dist} -> {dist(new_x, new_y)}"
        )

        return True

    def place_unit(self, unit, x, y):
        # 放置單位前先檢查是否在地圖內
        if not self.is_inside(x, y):
            print("invalid position")
            return False

        # 把 unit 放到指定座標
        self.positions[unit] = (x, y)
        return True

    def range_distance(self, unit_a, unit_b):
        # 用直線距離計算射程距離
        x1, y1 = self.positions[unit_a]
        x2, y2 = self.positions[unit_b]

        range_distance = int(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
        return range_distance

    def distance(self, unit_a, unit_b):
        # 用 Chebyshev distance 計算格子距離
        x1, y1 = self.positions[unit_a]
        x2, y2 = self.positions[unit_b]

        distance = max(abs(x2 - x1), abs(y2 - y1))
        return distance