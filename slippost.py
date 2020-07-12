import glob
import slippi as sl
from slippi import event
from slippi.id import ActionState
from slippi.util import EofException
from collections import Counter, namedtuple

from typing import Dict, Hashable, Callable, Iterable, List

STATE_GROUPS = {
    frozenset({ActionState.WAIT, ActionState.SQUAT_WAIT}): "WAIT",
    frozenset({ActionState.WALK_FAST, ActionState.WALK_MIDDLE, ActionState.WALK_SLOW}): "WALK",
    frozenset({ActionState.DASH}): "DASH",
}


LOGS_DIR = "/Users/markvan/Slippi/*.slp"


def load(f="/Users/markvan/Slippi/Game_20200710T220209.slp"):
    return sl.Game(f)


def load_all(logs_dir: str = LOGS_DIR) -> Iterable[sl.Game]:
    for gamefile in glob.glob(logs_dir)[:5]:
        try:
            yield load(gamefile)
        except Exception as e:
            print("Unable to load {}: {}".format(gamefile, e))


def states(game, port=0):
    return [f.ports[port].leader.post.state for f in game.frames]


def flags(game, port=0):
    return [f.ports[port].leader.post.flags for f in game.frames]


def hitstun_buttons(game, port=0):
    return [
        tuple(sorted(f.ports[port].leader.pre.buttons.physical.pressed()))
        if f.ports[port].leader.post.hit_stun
        else ()
        for f in game.frames
    ]


def _hitstun_buttons(port_data: event.Frame.Port.Data):
    return _buttons(port_data) if port_data.post.hit_stun > 0 else "(not in hitstun)"


def buttons(game, port=0):
    return [tuple(sorted(f.ports[port].leader.pre.buttons.physical.pressed())) for f in game.frames]


def _fmt_buttons(buttons):
    if buttons and isinstance(buttons, (tuple, list)):
        return ",".join(b.name for b in sorted(buttons))
    elif buttons:
        return buttons.name
    else:
        return "(no input)"


def _buttons(port_data: event.Frame.Port.Data):
    return _fmt_buttons(port_data.pre.buttons.physical.pressed())


def _state_group(port_data: event.Frame.Port.Data):
    for groupset, name in STATE_GROUPS.items():
        if port_data.post.state in groupset:
            return name
    return "OTHER"


def _state(port_data: event.Frame.Port.Data):
    return port_data.post.state.name


FRAME_DATA_HANDLERS: Dict[str, Callable] = {
    "buttons": _buttons,
    "hitstun_buttons": _hitstun_buttons,
    "state_group": _state_group,
    "full_state": _state,
}


def _handle_frame_port(port: event.Frame.Port) -> Dict[str, Hashable]:
    return {stat_name: handler(port.leader) for stat_name, handler in FRAME_DATA_HANDLERS.items()}


def _handle_frame(frame: event.Frame) -> Dict[int, Dict[str, Hashable]]:
    """Given a frame, return {port: {stat_name: stat_str, ...}, ...}."""
    return {i: _handle_frame_port(frame_port) for i, frame_port in enumerate(frame.ports) if frame_port}


def _print_player_stats(player_name, counters):
    print(player_name)
    for stats_key, counter in counters.items():
        print(f"  {stats_key}")
        total = sum(counter.values())
        # print("\n".join(f"    {100*count/total:5.2f}%   ({count:6})   {stat}" for stat, count in counter.most_common()[:10]))
        print("\n".join(f"    {100*count/total:5.1f} %   {stat}" for stat, count in counter.most_common()[:10]))


def _summarize_player_frames(
    player_name: str, frame_stats: List[Dict[str, Hashable]], log=True
) -> Dict[str, Counter]:
    """Given a player name, and a list of framewise summaries, print and return whole-game counts.

    Args:
          player_name (str):
          frame_stats (List): Each element is a dict of frame "summaries" defined by FRAME_DATA_HANDLERS,
            e.g. {"hitstun_buttons": "L,A", "full_state": "JUMP_F"}

    Returns:
        Dict[str, Counter[str]]: Counts of frame summaries for whole game, e.g.:
            {"hitstun_buttons": {"L,A": 102, "A": 25, ...}, "full_state": {"JUMP_F": 309, ... } }
            
    """
    stats_keys = frame_stats[0].keys()
    counters = {stats_key: Counter(fs[stats_key] for fs in frame_stats) for stats_key in stats_keys}
    if log:
        _print_player_stats(player_name, counters)
    return counters


def game_summary(g: sl.Game) -> Dict[str, Dict[str, Counter]]:
    """Given a game, return a mapping of player name to summary statistics counters.

    Returns:
        {
            "Shep ({InGameCharacter.MARIO: 14280})": {
                "buttons": Counter(..),
                "hitstun_buttons": Counter(..),
                ..
            },
            "markvan ({InGameCharacter.MARTH: 14280})": {
                "buttons": Counter(..),
                "hitstun_buttons": Counter(..),
                ..
            },
        }

    """
    framewise_summaries = [_handle_frame(f) for f in g.frames]
    player_summaries = {}
    for i, player in enumerate(p for p in g.metadata.players if p):
        player_key = f"{player.netplay_name} ({list(player.characters.keys())[0].name})"
        player_summaries[player_key] = _summarize_player_frames(
            player_key, [f[i] for f in framewise_summaries], log=False
        )
    return player_summaries


def _union_keys(first, second):
    return list(set(first.keys()).union(set(second.keys())))


def _merge_player_stats(first: Dict[str, Counter], second: Dict[str, Counter]) -> Dict[str, Counter]:
    return {
        stat_name: first.get(stat_name, Counter()) + second.get(stat_name, Counter())
        for stat_name in _union_keys(first, second)
    }


def merge_game_stats(
    first: Dict[str, Dict[str, Counter]], second: Dict[str, Dict[str, Counter]]
) -> Dict[str, Dict[str, Counter]]:
    return {
        player_name: _merge_player_stats(first.get(player_name, {}), second.get(player_name, {}))
        for player_name in _union_keys(first, second)
    }


combined_stats = {}
for i, game in enumerate(load_all()):
    this_game_stats = game_summary(game)
    print("Processed game {}: {}".format(i, " vs. ".join(list(this_game_stats.keys()))))
    combined_stats = merge_game_stats(combined_stats, this_game_stats)

for player, player_stats in combined_stats.items():
    _print_player_stats(player, player_stats)
