bind = "unix:/var/www/research-people/research-people.sock"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
chdir = "/var/www/research-people"
accesslog = "-"
errorlog = "-"