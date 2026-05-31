import random
from logger import BattleRecorder

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
        BattleRecorder.start_tick(tick)

        # 用 self.units[:] 生成快照，避免戰鬥中刪除單位影響 loop
        for attacker in self.units[:]:

            # 若單位仍活著，開始記錄該單位本 tick 的行動
            if attacker.body.hp > 0:
                BattleRecorder.start_unit(attacker)

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
            BattleRecorder.log("TARGET_SELECT", target=target, score=max_score)

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
        BattleRecorder.log("TARGET_SELECT", target=target, score=max_score)

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
            BattleRecorder.log("MISS", target=target, accuracy=attacker.weapon.accuracy)

            self.updateunit()
            return

        # 如果 attacker unstable，傷害減半
        if attacker.body.state() == "unstable":
            dmg //= 2

        # 扣除 target HP
        target.body.hp -= dmg

        # 記錄 ATTACK 事件
        BattleRecorder.log(
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
            BattleRecorder.log(
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
            BattleRecorder.start_turn(turn + 1)

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