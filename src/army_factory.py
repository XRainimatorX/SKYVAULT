import random
from models import humanbody, groundweapon, groundunit
# 生成 RED team

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