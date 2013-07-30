
import pkgutil

modules = []

for i in [name for _, name, _ in pkgutil.iter_modules(['modules'])]:
    exec("from modules.%s import Module" % i)
    exec("modules.append(Module)")

class API (*modules):

    pass
