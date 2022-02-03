def save_workflow(workflow, filename):
    from yaml import dump
    with open(filename + '.yaml', 'w') as stream:
        dump(workflow,stream)

def load_workflow(filename):
    from yaml import unsafe_load
    with open(filename, "rb") as stream:
        return unsafe_load(stream)