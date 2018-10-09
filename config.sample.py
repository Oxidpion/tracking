class Config:

    def __init__(self):
        self.token = 'TOKEN'

        self.redmine_host = 'https://task.org'
        self.redmine_general_issue = {
            1: 'Education',
            24: 'Task',
        }

        self.proxy_url = 'socks5://proxy_url:port'
        self.proxy_username = 'proxy_username'
        self.proxy_password = 'proxy_password'

        self.dsn_db = 'sqlite:///sqlite.db'