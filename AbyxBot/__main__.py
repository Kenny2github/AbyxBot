import os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from AbyxBot import done, run

try:
    run()
except KeyboardInterrupt:
    pass
finally:
    done()