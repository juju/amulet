
import amulet as juju
import amulet.environment as env
import amulet.expect 

env.deploy('wordpress')
env.deploy('mysql')
env.deploy('nfs')

env.configure('wordpress', {tuning: 'foo'})

env.relate('wordpress', 'mysql')
env.relate('wordpress', 'nfs')

env.expose('wordpress')
env.setup()

expect.http_status('wordpress', 200)
juju.deploy('memcached')
juju.wait(300)
expect.file_exists('wordpress/0', '/var/www/wordpress/wp-content/advanced-cache.php')
