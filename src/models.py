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

