import json
import sqlite3
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

@register("astrbot_plugin_trpg_player", "tinker", "跑团玩家角色卡插件", "1.0.0", "https://github.com/AstrBotDevs/astrbot_plugin_trpg_player")
class TRPGPlayerPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.super_admins = self.config.get("super_admins", [])
        self.plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_trpg_player"
        self.plugin_data_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.plugin_data_path / "trpg_player.db"
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 玩家角色表 (全局)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    qq_user_id TEXT PRIMARY KEY,
                    character_name TEXT NOT NULL,
                    gender TEXT,
                    strength INTEGER DEFAULT 10,
                    speed INTEGER DEFAULT 10,
                    intelligence INTEGER DEFAULT 10,
                    stamina INTEGER DEFAULT 10,
                    spirit INTEGER DEFAULT 10,
                    immunity INTEGER DEFAULT 10,
                    score INTEGER DEFAULT 1000,
                    items TEXT DEFAULT '[]',
                    skills TEXT DEFAULT '[]',
                    bloodline TEXT DEFAULT '无',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def _is_super_admin(self, qq_user_id: str) -> bool:
        return qq_user_id in self.super_admins

    def _get_target_qq(self, event: AstrMessageEvent, text_fallback: str) -> str:
        """从消息中提取目标QQ，优先提取At组件，其次使用文本兜底"""
        for comp in event.get_messages():
            if isinstance(comp, At):
                return str(comp.qq)
        return text_fallback.strip()

    @filter.command("登记")
    async def register_player(self, event: AstrMessageEvent, character_name: str = ""):
        '''登记一个新的角色卡: /登记 [角色名]'''
        if not character_name:
            yield event.plain_result("请提供角色名，格式：/登记 [角色名]")
            return

        qq_user_id = str(event.get_sender_id())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT character_name FROM players WHERE qq_user_id = ?", (qq_user_id,))
            if cursor.fetchone():
                yield event.plain_result("您已经登记过角色了，目前每位用户仅支持一张角色卡。")
                return

            gender = "未知"
            # 尝试从 aiocqhttp 适配器获取性别信息
            if event.get_platform_name() == "aiocqhttp":
                try:
                    # event.message_obj 可能是 AstrBotMessage，里面带有 bot(即 CQHttp client) 和 raw_message
                    bot = getattr(event.message_obj, "bot", None)
                    if not bot and hasattr(event, "bot"):
                        bot = event.bot

                    if bot and hasattr(bot, "call_action"):
                        user_info = await bot.call_action("get_stranger_info", user_id=int(qq_user_id), no_cache=False)
                        if user_info and "sex" in user_info:
                            sex_map = {"male": "男", "female": "女", "unknown": "未知"}
                            gender = sex_map.get(user_info["sex"], "未知")
                except Exception as e:
                    # 获取失败或接口不支持时，保留默认的“未知”
                    pass

            cursor.execute('''
                INSERT INTO players (qq_user_id, character_name, gender)
                VALUES (?, ?, ?)
            ''', (qq_user_id, character_name, gender))
            conn.commit()

        yield event.plain_result(f"角色「{character_name}」登记成功！初始属性已设置为10，积分1000点。使用 /面板 查看详细信息。")

    @filter.command("修改姓名")
    async def change_character_name(self, event: AstrMessageEvent, new_name: str = ""):
        '''修改自己的角色姓名: /修改姓名 [新姓名]'''
        if not new_name:
            yield event.plain_result("请提供新的角色名，格式：/修改姓名 [新姓名]")
            return

        qq_user_id = str(event.get_sender_id())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT character_name FROM players WHERE qq_user_id = ?", (qq_user_id,))
            if not cursor.fetchone():
                yield event.plain_result("您还没有登记角色，请先使用 /登记 [角色名] 进行登记。")
                return

            cursor.execute('''
                UPDATE players
                SET character_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE qq_user_id = ?
            ''', (new_name, qq_user_id))
            conn.commit()

        yield event.plain_result(f"角色姓名已成功修改为「{new_name}」。")

    @filter.command("修改性别")
    async def change_character_gender(self, event: AstrMessageEvent, new_gender: str = ""):
        '''修改自己的角色性别: /修改性别 [新性别]'''
        if not new_gender:
            yield event.plain_result("请提供新的角色性别，格式：/修改性别 [新性别]")
            return

        qq_user_id = str(event.get_sender_id())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT character_name FROM players WHERE qq_user_id = ?", (qq_user_id,))
            if not cursor.fetchone():
                yield event.plain_result("您还没有登记角色，请先使用 /登记 [角色名] 进行登记。")
                return

            cursor.execute('''
                UPDATE players
                SET gender = ?, updated_at = CURRENT_TIMESTAMP
                WHERE qq_user_id = ?
            ''', (new_gender, qq_user_id))
            conn.commit()

        yield event.plain_result(f"角色性别已成功修改为「{new_gender}」。")

    @filter.command("面板")
    async def view_profile(self, event: AstrMessageEvent):
        '''查看当前角色的信息面板: /面板'''
        qq_user_id = str(event.get_sender_id())
        async for res in self._send_profile_panel(event, qq_user_id):
            yield res

    async def _send_profile_panel(self, event: AstrMessageEvent, target_qq: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM players WHERE qq_user_id = ?", (target_qq,))
            row = cursor.fetchone()

            if not row:
                if str(event.get_sender_id()) == target_qq:
                    yield event.plain_result("您还没有登记角色，请先使用 /登记 [角色名] 进行登记。")
                else:
                    yield event.plain_result(f"用户 {target_qq} 还没有登记角色。")
                return

            items = json.loads(row['items'])
            items_str = ", ".join(items) if items else "无"

            skills = json.loads(row['skills'])
            skills_str = ", ".join(skills) if skills else "无"

            gender_str = row['gender'] if row['gender'] else "未知"

            panel = (
                f"——个人信息——\n"
                f"QQ：{row['qq_user_id']}\n"
                f"姓名：{row['character_name']}\n"
                f"性别：{gender_str}\n"
                f"力量：{row['strength']}\n"
                f"速度：{row['speed']}\n"
                f"智力：{row['intelligence']}\n"
                f"体力：{row['stamina']}\n"
                f"精神力：{row['spirit']}\n"
                f"免疫力：{row['immunity']}\n"
                f"所得积分：{row['score']}\n"
                f"所得物品：{items_str}\n"
                f"技能：{skills_str}\n"
                f"血统：{row['bloodline']}"
            )

            yield event.plain_result(panel)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_stat_modification(self, event: AstrMessageEvent):
        '''处理属性修改，如 /力量 +1'''
        message = event.message_str.strip()

        # 匹配格式: /属性名 +数值 或 /属性名 -数值
        if not message.startswith("/"):
            return

        parts = message[1:].split()
        if len(parts) != 2:
            return

        stat_name = parts[0]
        op_val = parts[1]

        # 允许修改的属性映射 (不含积分，积分不能直接买卖)
        stat_map = {
            "力量": "strength",
            "速度": "speed",
            "智力": "intelligence",
            "体力": "stamina",
            "精神力": "spirit",
            "免疫力": "immunity"
        }

        if stat_name not in stat_map:
            return

        try:
            # 解析加减号和数值
            if op_val.startswith('+'):
                delta = int(op_val[1:])
            elif op_val.startswith('-'):
                delta = int(op_val) # 包含负号
            else:
                return # 格式不匹配

            if delta == 0:
                yield event.plain_result("修改数值不能为 0。")
                return
        except ValueError:
            return

        db_field = stat_map[stat_name]
        qq_user_id = str(event.get_sender_id())
        cost_per_point = 100
        total_cost = delta * cost_per_point  # 正数表示扣除积分，负数(退还属性)表示增加积分

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT character_name, score FROM players WHERE qq_user_id = ?", (qq_user_id,))
            row = cursor.fetchone()
            if not row:
                yield event.plain_result("您还没有登记角色，无法修改属性。请先使用 /登记 [角色名] 进行登记。")
                return

            current_score = row[1]

            # 检查积分是否足够 (购买属性时)
            if delta > 0 and current_score < total_cost:
                yield event.plain_result(f"积分不足！提升 {delta} 点{stat_name}需要 {total_cost} 积分，您当前只有 {current_score} 积分。")
                return

            # 更新属性和积分
            cursor.execute(f'''
                UPDATE players
                SET {db_field} = {db_field} + ?, score = score - ?, updated_at = CURRENT_TIMESTAMP
                WHERE qq_user_id = ?
            ''', (delta, total_cost, qq_user_id))
            conn.commit()

            # 获取更新后的值
            cursor.execute(f"SELECT {db_field}, score FROM players WHERE qq_user_id = ?", (qq_user_id,))
            updated_row = cursor.fetchone()
            new_val = updated_row[0]
            new_score = updated_row[1]

        if delta > 0:
            yield event.plain_result(f"消耗了 {total_cost} 积分，{stat_name}提升了 {delta} 点。当前{stat_name}：{new_val}，剩余积分：{new_score}")
        else:
            yield event.plain_result(f"退还了 {stat_name} {abs(delta)} 点，返还了 {abs(total_cost)} 积分。当前{stat_name}：{new_val}，剩余积分：{new_score}")

        # 成功处理指令后，拦截事件，防止继续传给大模型
        event.stop_event()

    # ================= 超级管理员特权指令 =================

    @filter.command("查看面板")
    async def admin_view_profile(self, event: AstrMessageEvent, target: str = ""):
        '''[超管] 查看他人面板: /查看面板 @某人 或 /查看面板 [QQ号]'''
        qq_user_id = str(event.get_sender_id())
        if not self._is_super_admin(qq_user_id):
            yield event.plain_result("权限不足，仅超级管理员可使用该指令。")
            return

        target_qq = self._get_target_qq(event, target)
        if not target_qq:
            yield event.plain_result("请指定目标，例如：/查看面板 @某人")
            return

        async for res in self._send_profile_panel(event, target_qq):
            yield res

    @filter.command("删除角色")
    async def admin_delete_player(self, event: AstrMessageEvent, target: str = ""):
        '''[超管] 删除某个用户的角色卡: /删除角色 @某人 或 /删除角色 [QQ号]'''
        qq_user_id = str(event.get_sender_id())
        if not self._is_super_admin(qq_user_id):
            yield event.plain_result("权限不足，仅超级管理员可使用该指令。")
            return

        target_qq = self._get_target_qq(event, target)
        if not target_qq:
            yield event.plain_result("请指定目标，例如：/删除角色 @某人")
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT character_name FROM players WHERE qq_user_id = ?", (target_qq,))
            row = cursor.fetchone()
            if not row:
                yield event.plain_result(f"未找到目标用户 {target_qq} 的角色卡。")
                return

            char_name = row[0]
            cursor.execute("DELETE FROM players WHERE qq_user_id = ?", (target_qq,))
            conn.commit()

        yield event.plain_result(f"已成功删除用户 {target_qq} 的角色「{char_name}」。")

    @filter.command("强制修改")
    async def admin_force_modify(self, event: AstrMessageEvent, target: str = "", stat_name: str = "", op_val: str = ""):
        '''[超管] 强制修改某个用户的六围属性、积分: /强制修改 @某人 [属性] [+/-数值]'''
        qq_user_id = str(event.get_sender_id())
        if not self._is_super_admin(qq_user_id):
            yield event.plain_result("权限不足，仅超级管理员可使用该指令。")
            return

        target_qq = self._get_target_qq(event, target)
        if not target_qq or not stat_name or not op_val:
            yield event.plain_result("指令格式错误，正确格式：/强制修改 @某人 [属性] [+/-数值]\n例如：/强制修改 @张三 力量 +10")
            return

        stat_map = {
            "力量": "strength", "速度": "speed", "智力": "intelligence",
            "体力": "stamina", "精神力": "spirit", "免疫力": "immunity", "积分": "score"
        }

        if stat_name not in stat_map:
            yield event.plain_result(f"未知属性「{stat_name}」。可选属性：{', '.join(stat_map.keys())}")
            return

        try:
            if op_val.startswith('+'):
                delta = int(op_val[1:])
            elif op_val.startswith('-'):
                delta = int(op_val)
            else:
                yield event.plain_result("数值必须以 + 或 - 开头，例如：+10")
                return
        except ValueError:
            yield event.plain_result("无效的数值格式。")
            return

        db_field = stat_map[stat_name]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT character_name FROM players WHERE qq_user_id = ?", (target_qq,))
            if not cursor.fetchone():
                yield event.plain_result(f"未找到目标用户 {target_qq} 的角色卡。")
                return

            cursor.execute(f'''
                UPDATE players
                SET {db_field} = {db_field} + ?, updated_at = CURRENT_TIMESTAMP
                WHERE qq_user_id = ?
            ''', (delta, target_qq))
            conn.commit()

            cursor.execute(f"SELECT {db_field} FROM players WHERE qq_user_id = ?", (target_qq,))
            new_val = cursor.fetchone()[0]

        action = "增加" if delta > 0 else "减少"
        yield event.plain_result(f"已强制修改用户 {target_qq} 的 {stat_name}：{action} {abs(delta)} 点，当前{stat_name}为：{new_val}")

    @filter.command("增加物品")
    async def admin_add_item(self, event: AstrMessageEvent, target: str = "", item_name: str = ""):
        '''[超管] 给某人增加物品: /增加物品 @某人 [物品名]'''
        await self._modify_list_field(event, target, item_name, "items", "增加物品") # type: ignore #ignore

    @filter.command("删除物品")
    async def admin_remove_item(self, event: AstrMessageEvent, target: str = "", item_name: str = ""):
        '''[超管] 给某人删除物品: /删除物品 @某人 [物品名]'''
        await self._modify_list_field(event, target, item_name, "items", "删除物品") # type: ignore #ignore

    @filter.command("增加技能")
    async def admin_add_skill(self, event: AstrMessageEvent, target: str = "", skill_name: str = ""):
        '''[超管] 给某人增加技能: /增加技能 @某人 [技能名]'''
        await self._modify_list_field(event, target, skill_name, "skills", "增加技能") # type: ignore #ignore

    @filter.command("删除技能")
    async def admin_remove_skill(self, event: AstrMessageEvent, target: str = "", skill_name: str = ""):
        '''[超管] 给某人删除技能: /删除技能 @某人 [技能名]'''
        await self._modify_list_field(event, target, skill_name, "skills", "删除技能") # type: ignore #ignore

    async def _modify_list_field(self, event: AstrMessageEvent, target: str, element_name: str, db_field: str, action: str):
        qq_user_id = str(event.get_sender_id())
        if not self._is_super_admin(qq_user_id):
            yield event.plain_result("权限不足，仅超级管理员可使用该指令。")
            return

        target_qq = self._get_target_qq(event, target)
        if not target_qq or not element_name:
            yield event.plain_result(f"指令格式错误，正确格式：/{action} @某人 [{action[-2:]}名]")
            return

        is_add = "增加" in action

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT character_name, {db_field} FROM players WHERE qq_user_id = ?", (target_qq,))
            row = cursor.fetchone()
            if not row:
                yield event.plain_result(f"未找到目标用户 {target_qq} 的角色卡。")
                return

            char_name = row[0]
            elements = json.loads(row[1])

            if is_add:
                elements.append(element_name)
                msg = f"成功向用户 {target_qq}（{char_name}）的{action[-2:]}列表中添加：「{element_name}」"
            else:
                if element_name in elements:
                    elements.remove(element_name)
                    msg = f"成功从用户 {target_qq}（{char_name}）的{action[-2:]}列表中移除：「{element_name}」"
                else:
                    msg = f"用户 {target_qq} 的{action[-2:]}列表中没有找到：「{element_name}」"

            elements_str = json.dumps(elements, ensure_ascii=False)
            cursor.execute(f'''
                UPDATE players
                SET {db_field} = ?, updated_at = CURRENT_TIMESTAMP
                WHERE qq_user_id = ?
            ''', (elements_str, target_qq))
            conn.commit()

        yield event.plain_result(msg)
