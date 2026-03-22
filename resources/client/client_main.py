from resources.client import render


class Client:
    def __init__(self):
        self.version = "0.0.1 SNAPSHOT"
        self.render = render.Render()

    def start(self):
        self.render.start()