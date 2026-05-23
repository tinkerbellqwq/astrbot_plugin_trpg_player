import json
import sqlite3
from pathlib import Path
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

@register("astrbot_plugin_trpg_player", "tinker", "跑团玩家角色卡插件", "1.0.0", "https://github.com/AstrBotDevs/astrbot_plugin_trpg_player")
class TRPGPlayerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
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

            cursor.execute('''
                INSERT INTO players (qq_user_id, character_name)
                VALUES (?, ?)
            ''', (qq_user_id, character_name))
            conn.commit()

        yield event.plain_result(f"角色「{character_name}」登记成功！初始属性已设置为10，积分1000点。使用 /面板 查看详细信息。")

    @filter.command("面板")
    async def view_profile(self, event: AstrMessageEvent):
        '''查看当前角色的信息面板: /面板'''
        qq_user_id = str(event.get_sender_id())

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM players WHERE qq_user_id = ?", (qq_user_id,))
            row = cursor.fetchone()

            if not row:
                yield event.plain_result("您还没有登记角色，请先使用 /登记 [角色名] 进行登记。")
                return

            items = json.loads(row['items'])
            items_str = ", ".join(items) if items else "无"

            skills = json.loads(row['skills'])
            skills_str = ", ".join(skills) if skills else "无"

            gender_str = row['gender'] if row['gender'] else "未知"

            panel = (
                f"——个人信息——\n"
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

        # 允许修改的属性映射
        stat_map = {
            "力量": "strength",
            "速度": "speed",
            "智力": "intelligence",
            "体力": "stamina",
            "精神力": "spirit",
            "免疫力": "immunity",
            "积分": "score"
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
        except ValueError:
            return

        db_field = stat_map[stat_name]
        qq_user_id = str(event.get_sender_id())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT character_name FROM players WHERE qq_user_id = ?", (qq_user_id,))
            if not cursor.fetchone():
                yield event.plain_result("您还没有登记角色，无法修改属性。请先使用 /登记 [角色名] 进行登记。")
                return

            cursor.execute(f'''
                UPDATE players
                SET {db_field} = {db_field} + ?, updated_at = CURRENT_TIMESTAMP
                WHERE qq_user_id = ?
            ''', (delta, qq_user_id))
            conn.commit()

            # 获取更新后的值
            cursor.execute(f"SELECT {db_field} FROM players WHERE qq_user_id = ?", (qq_user_id,))
            new_val = cursor.fetchone()[0]

        action = "增加" if delta > 0 else "减少"
        yield event.plain_result(f"{stat_name}已{action} {abs(delta)} 点，当前{stat_name}：{new_val}")
