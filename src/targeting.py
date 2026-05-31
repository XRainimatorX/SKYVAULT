import random

def threatscore(attacker, enemies):
    # 存放每個敵人的 threat score
    threat_list = []

    # 不同 attacker role 使用不同權重
    # 權重順序：hp, ap, dmg, role
    weight_matrix = {
        "ASSAULT": [0.4, 0.2, 0.3, 0.1],
        "SUPPORT": [0.2, 0.1, 0.5, 0.2],
        "COMMAND": [0.2, 0.1, 0.2, 0.5],
    }

    # # 不同敵方 role 的價值分數
    # role_score = {
    #     "ASSAULT": 20,
    #     "SUPPORT": 30,
    #     "COMMAND": 50
    # }

    # # 對每一個敵人計算威脅分數
    # for u in eneimes:
    #     # feature vector：
    #     # 1. HP 脆弱度：HP 越低分越高
    #     # 2. AP
    #     # 3. 武器傷害
    #     # 4. role 分數
    #     variable_list = [
    #         5 * (120 - u.body.hp) / 6,
    #         u.body.ap,
    #         u.weapon.dmg,
    #         role_score[u.role]
    #     ]

    #     # weighted score = weight vector × feature vector
    #     threat_score = sum(
    #         x * y / 100
    #         for x, y in zip(weight_matrix[attacker.role], variable_list)
    #     )

    #     threat_list.append(threat_score)

    threat_list = target_score(attacker, enemies, weight_matrix)

    # 找出最高分
    max_score = max(threat_list)

    # 如果有多個最高分目標，隨機選一個
    target = random.choice([
        enemy for enemy, score in zip(enemies, threat_list)
        if score == max_score
    ])

    # 用於 print 顯示選擇結果
    selection = attacker.team, attacker.name, f"selected {target.name} with score {max_score * 100:.0f}"

    return target, selection, max_score

def target_score(attacker, enemies, weight_matrix):

    # Set up empty list to add in threat scores
    threat_list = []

    # 不同敵方 role 的價值分數
    role_score = {
        "ASSAULT": 20,
        "SUPPORT": 30,
        "COMMAND": 50
    }

    # 對每一個敵人計算威脅分數
    for u in enemies:
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

    return threat_list
