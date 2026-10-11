"""Small 'touch grass' prompts that pull attention off the screen and onto the walk."""
import random

CHALLENGES = [
    "Tiny challenge: find something green that isn't a leaf, and tell me what it is.",
    "Pause for ten seconds and count how many different sounds you can hear. Tell me how many.",
    "Find the oldest looking tree nearby, and tell me what makes it look old.",
    "Touch a leaf or a patch of bark, and tell me what it feels like.",
    "Look up for ten seconds. Tell me what you notice in the sky or the branches.",
    "Find something that is moving without you touching it, and tell me what it is.",
    "Take three slow breaths and notice the air. Tell me what you smell.",
    "Spot three different shades of green, and tell me where they are.",
    "Listen for the farthest sound you can hear, and tell me what it is.",
    "Find a flower, even a tiny one, and tell me its colour.",
    "Find a small insect or animal and watch it for ten seconds. Tell me what it did.",
    "Find a shadow with an interesting shape, and tell me what it looks like.",
]


def next_challenge(used: set[int], rng=random) -> tuple[int, str]:
    """Pick a challenge not used yet this walk; start over once all have been used."""
    if len(used) >= len(CHALLENGES):
        used.clear()
    idx = rng.choice([i for i in range(len(CHALLENGES)) if i not in used])
    used.add(idx)
    return idx, CHALLENGES[idx]