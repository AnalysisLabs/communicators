# /home/guatamap/Analysis Labs/Dev Tools/com-branches/orchestrated-1/communicators/control-layer-methods/landscaping.py

from prelude.standard import*
from prelude.internal_lib import*

initialize_namespace("ConfigState", "IdealState", "RealState", "TempState")
config_state = yaml.safe_load(Path(sys.argv[1]).read_text())
populate_namespace("ConfigState", config_state)
ideal_state = yaml.safe_load(Path(config_state.ideal_path).read_text())
populate("IdealState", ideal_state)
