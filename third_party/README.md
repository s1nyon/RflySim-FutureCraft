# Third-party dependencies

Third-party source is not project mission code and is not edited through the
main repository. `ego-planner-swarm` is a separate Catkin overlay pinned as a
Git submodule to the team's fork.

Build order:

1. `/opt/ros/noetic/setup.bash`
2. `third_party/ego-planner-swarm/devel/setup.bash`
3. `future_aircraft_ws/devel/setup.bash`

Dependency updates require a reviewed commit in the dependency repository,
an exact submodule pointer update, the repository contract suite, and the
Stage 6C/6D/7/8 regression suites. Never edit generated `build/` or `devel/`
products as source.
