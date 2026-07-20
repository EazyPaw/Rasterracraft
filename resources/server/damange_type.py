from abc import ABC

from resources.server.tags import DamageTag


class DamageType(ABC):
    exhaustion = 0.1
    message_id = ''
    scaling = 'when_caused_by_living_non_player'
    tags = ()

    @classmethod
    def has_tag(cls, tag: DamageTag) -> bool:
        return tag in cls.tags or tag.value in cls.tags

    @classmethod
    def get_death_info(cls, *args):
        """Return a language-independent parameterized death message payload."""
        return {"key": f"death.attack.{cls.message_id}", "args": list(args)}

class ARROW(DamageType):
    exhaustion = 0.1
    message_id = 'arrow'
    scaling = 'when_caused_by_living_non_player'

class BAD_RESPAWN_POINT(DamageType):
    death_message_type = 'intentional_game_design'
    exhaustion = 0.1
    message_id = 'badRespawnPoint'
    scaling = 'always'

class CACTUS(DamageType):
    exhaustion = 0.1
    message_id = 'cactus'
    scaling = 'when_caused_by_living_non_player'

class CRAMMING(DamageType):
    exhaustion = 0.0
    message_id = 'cramming'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class DRAGON_BREATH(DamageType):
    exhaustion = 0.0
    message_id = 'dragonBreath'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class DROWN(DamageType):
    effects = 'drowning'
    exhaustion = 0.0
    message_id = 'drown'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class DRY_OUT(DamageType):
    exhaustion = 0.1
    message_id = 'dryout'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class EXPLOSION(DamageType):
    exhaustion = 0.1
    message_id = 'explosion'
    scaling = 'always'

class FALL(DamageType):
    death_message_type = 'fall_variants'
    exhaustion = 0.0
    message_id = 'fall'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class FALLING_ANVIL(DamageType):
    exhaustion = 0.1
    message_id = 'anvil'
    scaling = 'when_caused_by_living_non_player'

class FALLING_BLOCK(DamageType):
    exhaustion = 0.1
    message_id = 'fallingBlock'
    scaling = 'when_caused_by_living_non_player'

class FALLING_STALACTITE(DamageType):
    exhaustion = 0.1
    message_id = 'fallingStalactite'
    scaling = 'when_caused_by_living_non_player'

class FIREBALL(DamageType):
    effects = 'burning'
    exhaustion = 0.1
    message_id = 'fireball'
    scaling = 'when_caused_by_living_non_player'

class FIREWORKS(DamageType):
    exhaustion = 0.1
    message_id = 'fireworks'
    scaling = 'when_caused_by_living_non_player'

class FLY_INTO_WALL(DamageType):
    exhaustion = 0.0
    message_id = 'flyIntoWall'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class FREEZE(DamageType):
    effects = 'freezing'
    exhaustion = 0.0
    message_id = 'freeze'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class GENERIC(DamageType):
    exhaustion = 0.0
    message_id = 'generic'
    scaling = 'when_caused_by_living_non_player'

class HOT_FLOOR(DamageType):
    effects = 'burning'
    exhaustion = 0.1
    message_id = 'hotFloor'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class IN_FIRE(DamageType):
    effects = 'burning'
    exhaustion = 0.1
    message_id = 'inFire'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class IN_WALL(DamageType):
    exhaustion = 0.0
    message_id = 'inWall'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class INDIRECT_MAGIC(DamageType):
    exhaustion = 0.0
    message_id = 'indirectMagic'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class LAVA(DamageType):
    effects = 'burning'
    exhaustion = 0.1
    message_id = 'lava'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class LIGHTNING_BOLT(DamageType):
    exhaustion = 0.1
    message_id = 'lightningBolt'
    scaling = 'when_caused_by_living_non_player'

class MAGIC(DamageType):
    exhaustion = 0.0
    message_id = 'magic'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class MOB_ATTACK(DamageType):
    exhaustion = 0.1
    message_id = 'mob'
    scaling = 'when_caused_by_living_non_player'

class MOB_ATTACK_NO_AGGRO(DamageType):
    exhaustion = 0.1
    message_id = 'mob'
    scaling = 'when_caused_by_living_non_player'

class MOB_PROJECTILE(DamageType):
    exhaustion = 0.1
    message_id = 'mob'
    scaling = 'when_caused_by_living_non_player'

class ON_FIRE(DamageType):
    effects = 'burning'
    exhaustion = 0.0
    message_id = 'onFire'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class OUT_OF_WORLD(DamageType):
    exhaustion = 0.0
    message_id = 'outOfWorld'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR, DamageTag.BYPASSES_COOLDOWN)

class PLAYER_ATTACK(DamageType):
    exhaustion = 0.1
    message_id = 'player'
    scaling = 'when_caused_by_living_non_player'

class PLAYER_EXPLOSION(DamageType):
    exhaustion = 0.1
    message_id = 'explosion.player'
    scaling = 'always'

class SONIC_BOOM(DamageType):
    exhaustion = 0.0
    message_id = 'sonic_boom'
    scaling = 'always'
    tags = (DamageTag.BYPASSES_ARMOR,)

class STALAGMITE(DamageType):
    exhaustion = 0.0
    message_id = 'stalagmite'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class STARVE(DamageType):
    exhaustion = 0.0
    message_id = 'starve'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class STING(DamageType):
    exhaustion = 0.1
    message_id = 'sting'
    scaling = 'when_caused_by_living_non_player'

class SWEET_BERRY_BUSH(DamageType):
    effects = 'poking'
    exhaustion = 0.1
    message_id = 'sweetBerryBush'
    scaling = 'when_caused_by_living_non_player'

class THORNS(DamageType):
    effects = 'thorns'
    exhaustion = 0.1
    message_id = 'thorns'
    scaling = 'when_caused_by_living_non_player'

class THROWN(DamageType):
    exhaustion = 0.1
    message_id = 'thrown'
    scaling = 'when_caused_by_living_non_player'

class TRIDENT(DamageType):
    exhaustion = 0.1
    message_id = 'trident'
    scaling = 'when_caused_by_living_non_player'

class UNATTRIBUTED_FIREBALL(DamageType):
    effects = 'burning'
    exhaustion = 0.1
    message_id = 'onFire'
    scaling = 'when_caused_by_living_non_player'

class WITHER(DamageType):
    exhaustion = 0.0
    message_id = 'wither'
    scaling = 'when_caused_by_living_non_player'
    tags = (DamageTag.BYPASSES_ARMOR,)

class WITHER_SKULL(DamageType):
    exhaustion = 0.1
    message_id = 'witherSkull'
    scaling = 'when_caused_by_living_non_player'
