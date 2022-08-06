# api access details
API_BASE = "https://autorender.portal2.sr/api/v1"
API_UNAME = ...
API_PWORD = ...

# the address of the cm boards
BOARDS_BASE = "https://board.portal2.sr"

# the path to the root portal 2 directory
PORTAL2_DIR = ...

# the name of a short dummy demo, used to confirm rendering works
DUMMY_DEMO = "dummy"
# the name of the rendering config that should be executed
RENDER_CFG = "render"

# the name of a temporary directory to store renders in while they upload
RENDER_TMP_DIR = "renders_tmp"

# the constant duration to add to the render timeout, in seconds
RENDER_TIMEOUT_BASE = 30
# the factor to multiply demo duration by to find the timeout
# this should be set to a bit over 1/render_speed
RENDER_TIMEOUT_FACTOR = 7
