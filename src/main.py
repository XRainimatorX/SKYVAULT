import random  # 匯入 random，用於隨機命中、隨機選目標、隨機血量等


# =========================
# 身體 / 狀態系統
# =========================
class humanbody:
    def __init__(self, hp, ap, hunger):
        # hp = 生命值
        self.hp = hp

        # hunger = 飢餓 / 補給狀態，目前用來判斷 unstable
        self.hunger = hunger

        # ap = 行動力，目前移動會消耗 AP
        self.ap = ap

    def state(self):
        # hp 歸零或低於 0，單位被摧毀
        if self.hp <= 0:
            return "destroyed"

        # AP 或 hunger 低於 / 等於 0，單位進入不穩定狀態
        if any(x <= 0 for x in (self.ap, self.hunger)):
            return "unstable"

        # 其他情況則為正常可行動狀態
        return "active"

    def __repr__(self):
        # 方便 print body 時顯示 hp, ap, hunger
        return f"{self.hp}, {self.ap}, {self.hunger}"


# =========================
# 武器系統
# =========================
class groundweapon:
    def __init__(self, weapon_name, dmg, attack_range, accuracy):
        # 武器名稱，例如 rifle / pistol / machine_gun
        self.weapon_name = weapon_name

        # 武器傷害
        self.dmg = dmg

        # 武器射程
        self.range = attack_range

        # 武器命中率，0.8 = 80%
        self.accuracy = accuracy

    def __repr__(self):
        # 顯示武器名稱、傷害、射程
        return f"{self.weapon_name}, {self.dmg}, {self.range}"


# =========================
# 單位系統
# =========================
class groundunit:
    def __init__(self, name, body, weapon, skill, role):
        # 單位名稱，例如 Rifleman / Squad Leader / Heavy_gunner
        self.name = name

        # 單位身體狀態，連到 humanbody object
        self.body = body

        # 單位武器，連到 groundweapon object
        self.weapon = weapon

        # 技能，目前可以是 None，未來可擴充
        self.skill = skill

        # 戰場職能，例如 ASSAULT / COMMAND / SUPPORT
        self.role = role

    def __repr__(self):
        # 顯示單位基本戰鬥資訊
        return f" {self.team}:{self.name}|HP:{self.body.hp}|Weapon:{self.weapon}|{self.role}"


# =========================
# 戰鬥流程管理器
# =========================
class UnitManager:

    def __init__(self, units):
        # 所有仍在戰場上的單位
        self.units = units

        # 已被摧毀的單位會存入這裡
        self.destoryed_store = []

    def tick(self, tick, turn):
        # 每個 tick 開始時，logger 開啟一個 tick 記錄區
        battle_recorder.start_tick(tick)

        # 用 self.units[:] 生成快照，避免戰鬥中刪除單位影響 loop
        for attacker in self.units[:]:

            # 若單位仍活著，開始記錄該單位本 tick 的行動
            if attacker.body.hp > 0:
                battle_recorder.start_unit(attacker)

            # 若單位 unstable，有 50% 機率不能行動
            if attacker.body.state() == "unstable":
                if random.random() < 0.5:
                    print(f"{attacker.team} : {attacker.name} failed to act (unstable)")
                    continue

                # unstable 但沒有失敗，仍可嘗試選目標
                self.choosetarget(attacker)

            # active 單位正常行動
            elif attacker.body.hp > 0 and attacker.body.state() == "active":
                self.choosetarget(attacker)

    def choosetarget(self, attacker):
        # 找出所有敵方且仍存活的單位
        enemies = [u for u in self.units if u.team != attacker.team and u.body.hp > 0]

        # 沒有敵人則無目標
        if not enemies:
            return None

        # 存放射程內敵人
        in_range_enemies = []

        # 檢查每個敵人是否在 attacker 射程內
        for enemy in enemies:
            in_range, distance = self.indistance(attacker, enemy)
            if in_range:
                in_range_enemies.append(enemy)

        # 如果有敵人在射程內，就只從射程內敵人選最高分目標
        if in_range_enemies:
            target, selection, max_score = self.theratscore(attacker, in_range_enemies)
            in_range, distance = self.indistance(attacker, target)

            print(" ".join(selection), "in a distance of", distance)

            # 記錄 target selection 事件
            battle_recorder.log("TARGET_SELECT", target=target, score=max_score)

            # 攻擊目標
            self.resolveaction(attacker, target)
            return True

        # 如果沒有敵人在射程內，從所有敵人中選最高分目標作為移動方向
        target, selection, max_score = self.theratscore(attacker, enemies)
        in_range, distance = self.indistance(attacker, target)

        print(
            f"no enemies in range, {attacker.team}:{attacker.name} "
            f"moves toward {target.team}:{target.name}, distance = {distance}"
        )

        # 記錄 target selection，即使是為了移動而選目標也記錄
        battle_recorder.log("TARGET_SELECT", target=target, score=max_score)

        # 呼叫 BattleMap 的 moving()，讓 attacker 向 target 靠近
        moved = battle_map.moving(attacker, target)

        # 如果成功移動，AP -1
        if moved:
            attacker.body.ap -= 1

        return False

    def indistance(self, attacker, target):
        # 使用 BattleMap 計算 attacker 和 target 的射程距離
        range_distance = battle_map.range_distance(attacker, target)

        # 若距離小於等於武器射程，代表可以攻擊
        if range_distance <= attacker.weapon.range:
            return True, range_distance
        else:
            return False, range_distance

    def theratscore(self, attacker, eneimes):
        # 存放每個敵人的 threat score
        threat_list = []

        # 不同 attacker role 使用不同權重
        # 權重順序：hp, ap, dmg, role
        weight_matrix = {
            "ASSAULT": [0.4, 0.2, 0.3, 0.1],
            "SUPPORT": [0.2, 0.1, 0.5, 0.2],
            "COMMAND": [0.2, 0.1, 0.2, 0.5],
        }

        # 不同敵方 role 的價值分數
        role_score = {
            "ASSAULT": 20,
            "SUPPORT": 30,
            "COMMAND": 50
        }

        # 對每一個敵人計算威脅分數
        for u in eneimes:
            # feature vector：
            # 1. HP 脆弱度：HP 越低分越高
            # 2. AP
            # 3. 武器傷害
            # 4. role 分數
            variable_list = [
                5 * (120 - u.body.hp) / 6,
                u.body.ap,
                u.weapon.dmg,
                role_score[u.role]
            ]

            # weighted score = weight vector × feature vector
            threat_score = sum(
                x * y / 100
                for x, y in zip(weight_matrix[attacker.role], variable_list)
            )

            threat_list.append(threat_score)

        # 找出最高分
        max_score = max(threat_list)

        # 如果有多個最高分目標，隨機選一個
        target = random.choice([
            enemy for enemy, score in zip(eneimes, threat_list)
            if score == max_score
        ])

        # 用於 print 顯示選擇結果
        selection = attacker.team, attacker.name, f"selected {target.name} with score {max_score * 100:.0f}"

        return target, selection, max_score

    def resolveaction(self, attacker, target):
        # 取得攻擊者武器傷害
        dmg = attacker.weapon.dmg

        # 記錄攻擊前目標 HP
        before = target.body.hp

        # 取得攻擊者武器命中率
        accuracy = attacker.weapon.accuracy

        # 命中率判定：random.random() > accuracy 則 miss
        if random.random() > attacker.weapon.accuracy:
            print(f"{attacker.team} : {attacker.name} attack failed")

            # 記錄 MISS 事件
            battle_recorder.log("MISS", target=target, accuracy=attacker.weapon.accuracy)

            self.updateunit()
            return

        # 如果 attacker unstable，傷害減半
        if attacker.body.state() == "unstable":
            dmg //= 2

        # 扣除 target HP
        target.body.hp -= dmg

        # 記錄 ATTACK 事件
        battle_recorder.log(
            "ATTACK",
            target=target,
            damage=dmg,
            hp_before=before,
            hp_after=target.body.hp
        )

        print(f"{attacker.team} : {attacker.name} attacks "
              f"{target.team} : {target.name} for {dmg} dmg → HP {before} → {target.body.hp}")

        # 攻擊後清理 destroyed 單位
        self.updateunit()

    def updateunit(self, destoryed=0):
        # 暫存需要移除的單位，避免邊 loop 邊刪 self.units
        to_remove = []

        # 找出 destroyed 單位
        for unit in self.units:
            if unit.body.state() == "destroyed":
                destoryed += 1
                to_remove.append(unit)

        # 從戰場移除 destroyed 單位
        for unit in to_remove:
            print(f" {unit.team} : {unit.name} destroyed ")

            # 記錄 DESTROYED 事件
            battle_recorder.log(
                "DESTROYED",
                target=unit,
                role=unit.role,
                final_hp=unit.body.hp
            )

            # 從 BattleMap 位置表移除
            battle_map.positions.pop(unit, None)

            # 從 active units 移除
            self.units.remove(unit)

            # 放入 destroyed store
            self.destoryed_store.append(unit)

        # 檢查目前還有幾個 team 存活
        alive_teams = set(u.team for u in self.units if u.body.hp > 0)

        # 如果少於 2 個 team，代表戰鬥結束
        if len(alive_teams) < 2:
            return True, next(iter(alive_teams))

        else:
            return False, None

    def run_turns(self, num_turns, ticks_per_turn):
        # 戰鬥開始前 summary
        print("parade before battle")
        self.summary(0)

        # 如果需要隨機行動順序，可打開這行
        # random.shuffle(self.units)

        # turn loop
        for turn in range(num_turns):

            # 每回合開始前先檢查是否已經勝負分明
            result, winner = self.updateunit()
            if result == True:
                break

            print(f"battle turn {turn + 1} starts")

            # Logger 開啟新 turn
            battle_recorder.start_turn(turn + 1)

            # tick loop
            for tick in range(ticks_per_turn):

                # 執行 tick
                self.tick(tick + 1, turn + 1)

                # 每 tick 後檢查是否勝負分明
                result, winner = self.updateunit()
                if result == True:
                    print(f"{winner} wins")
                    break

            print(f"--- Turn {turn + 1} ---")
            self.summary(turn + 1)

        print(f"--- final ---")
        self.summary(turn + 1)

    def summary(self, turns):
        # 每次 summary 都重新計算狀態數量
        destroyed = 0
        unstable = 0
        active = 0

        # 顯示仍在戰場上的單位狀態與位置
        for unit in self.units:
            print(unit, "state =", unit.body.state(), battle_map.positions[unit])

        # turn 0 只是開戰前展示，不統計 summary
        if turns != 0:
            for unit in self.destoryed_store + self.units:
                state = unit.body.state()
                if state == "destroyed":
                    destroyed += 1
                elif state == "unstable":
                    unstable += 1
                else:
                    active += 1

            print("Active:", active)
            print("Unstable:", unstable)
            print("Destroyed:", destroyed)
            return "summary complete"


# =========================
# 戰場空間系統
# =========================
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
        battle_recorder.log(
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


# =========================
# 建立武器、單位、隊伍、地圖、記錄器、戰鬥引擎
# =========================

# 武器資料
weapon_list = {
    "rifle": groundweapon("rifle", 10, 1, 0.8),
    "pistol": groundweapon("pistol", 6, 1, 0.6),
    "machine_gun": groundweapon("machine_gun", 20, 2, 0.55)
}

# 單位模板
ground_force = [
    groundunit("Rifleman", humanbody(100, 50, 50), weapon_list["rifle"], None, "ASSAULT"),
    groundunit("Squad Leader", humanbody(100, 100, 70), weapon_list["pistol"], None, "COMMAND"),
    groundunit("Heavy_gunner", humanbody(100, 50, 50), weapon_list["machine_gun"], None, "SUPPORT")
]

# 生成 RED team
red_team = [
    groundunit(
        u.name,
        humanbody(random.randint(80, 120), random.randint(40, 40), random.randint(2, 3)),
        u.weapon,
        u.skill,
        u.role
    )
    for u in ground_force
]

# 為 RED team 加上 team 屬性
list(map(lambda u: setattr(u, "team", "RED"), red_team))

# 生成 BLUE team
blue_team = [
    groundunit(
        u.name,
        humanbody(random.randint(80, 120), random.randint(40, 40), random.randint(2, 3)),
        u.weapon,
        u.skill,
        u.role
    )
    for u in ground_force
]

# 為 BLUE team 加上 team 屬性
list(map(lambda u: setattr(u, "team", "BLUE"), blue_team))

# 合併雙方參戰單位
Aramed_force = red_team + blue_team

# 建立戰場地圖
battle_map = BattleMap(10, 10)

# 建立戰鬥記錄器
battle_recorder = BattleRecorder()

# 建立戰鬥引擎
Battle_engine = BattleEngine(Aramed_force, battle_map)

# 開始戰鬥
Battle_engine.setup()

# 印出完整 battle recorder 結果
print(battle_recorder.turns)
