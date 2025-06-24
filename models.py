from __future__ import annotations

from typing import List, Dict, Optional

from pydantic import BaseModel, Field


class StatBlock(BaseModel):
    hp: float = 0
    atk: float = 0
    def_: float = Field(0, alias="def")
    spd: float = 0

    crit_rate: float = 0
    crit_dmg: float = 0
    effect_hit_rate: float = 0
    effect_res: float = 0
    break_effect: float = 0

    quantum_dmg: float = 0  # example for element-specific

    # any extra stats
    extra: Dict[str, float] = Field(default_factory=dict)


class RelicSubStat(BaseModel):
    id: int
    name: str
    value: float
    is_percent: bool = False


class Relic(BaseModel):
    id: int
    icon_path: str
    main_stat: str
    main_value: float
    level: int
    score: float = 0
    sub_stats: List[RelicSubStat] = Field(default_factory=list)


class LightCone(BaseModel):
    id: int
    icon_path: str
    level: int
    superimpose: int


class CharacterBuild(BaseModel):
    uid: int
    character_id: int
    name: str
    element: str
    path: str
    level: int
    eidolon: int

    stats: StatBlock
    light_cone: LightCone
    relics: List[Relic]

    portrait_path: str
    skill_img_path: Optional[str] = None 