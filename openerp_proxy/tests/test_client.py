from pkg_resources import parse_version

from . import BaseTestCase
from openerp_proxy.core import Client
from openerp_proxy.orm.object import Object
from openerp_proxy.orm.record import Record
from openerp_proxy.service.service import ServiceManager
from openerp_proxy.plugin import Plugin


class Test_10_Client(BaseTestCase):

    def setUp(self):
        super(self.__class__, self).setUp()
        self.client = Client(self.env.host,
                             dbname=self.env.dbname,
                             user=self.env.user,
                             pwd=self.env.password,
                             protocol=self.env.protocol,
                             port=self.env.port)

    def test_20_username(self):
        self.assertEqual(self.client.username, self.env.user)
        self.assertIsInstance(self.client.user, Record)
        self.assertEqual(self.client.user.login, self.env.user)

    def test_25_server_version(self):
        # Check that server version is wrapped in parse_version. thi allows to
        # compare versions
        self.assertIsInstance(self.client.server_version, type(parse_version('1.0.0')))


    def test_30_get_obj(self):
        self.assertIn('res.partner', self.client.registered_objects)
        obj = self.client.get_obj('res.partner')
        self.assertIsInstance(obj, Object)

        # Check object access in dictionary style
        self.assertIs(obj, self.client['res.partner'])

    def test_42_get_obj_wrong(self):
        self.assertNotIn('bad.object.name', self.client.registered_objects)
        with self.assertRaises(ValueError):
            self.client.get_obj('bad.object.name')

        with self.assertRaises(KeyError):
            self.client['bad.object.name']

    def test_50_to_url(self):
        url_tmpl = "%(protocol)s://%(user)s@%(host)s:%(port)s/%(dbname)s"
        cl_url = url_tmpl % self.env
        self.assertEqual(Client.to_url(self.client), cl_url)
        self.assertEqual(Client.to_url(self.env), cl_url)
        self.assertEqual(Client.to_url(None, **self.env), cl_url)
        self.assertEqual(self.client.get_url(), cl_url)

        with self.assertRaises(ValueError):
            Client.to_url('strange thing')

    def test_60_plugins(self):
        self.assertIn('Test', self.client.plugins.registered_plugins)
        self.assertIn('Test', self.client.plugins)
        self.assertIn('Test', dir(self.client.plugins))  # for introspection
        self.assertIsInstance(self.client.plugins.Test, Plugin)
        self.assertIsInstance(self.client.plugins['Test'], Plugin)
        self.assertIs(self.client.plugins['Test'], self.client.plugins.Test)

        # check plugin's method result
        self.assertEqual(self.client.get_url(), self.client.plugins.Test.test())

    def test_62_plugins_wrong_name(self):
        self.assertNotIn('Test_Bad', self.client.plugins.registered_plugins)
        self.assertNotIn('Test_Bad', self.client.plugins)
        self.assertNotIn('Test_Bad', dir(self.client.plugins))  # for introspection

        with self.assertRaises(KeyError):
            self.client.plugins['Test_Bad']

        with self.assertRaises(AttributeError):
            self.client.plugins.Test_Bad

    def test_70_client_services(self):
        self.assertIsInstance(self.client.services, ServiceManager)
        self.assertIn('db', self.client.services)
        self.assertIn('object', self.client.services)
        self.assertIn('report', self.client.services)

        self.assertIn('db', self.client.services.list)
        self.assertIn('object', self.client.services.list)
        self.assertIn('report', self.client.services.list)

        self.assertIn('db', dir(self.client.services))
        self.assertIn('object', dir(self.client.services))
        self.assertIn('report', dir(self.client.services))

    def test_80_execute(self):
        res = self.client.execute('res.partner', 'read', 1)
        self.assertIsInstance(res, dict)
        self.assertEqual(res['id'], 1)

        res = self.client.execute('res.partner', 'read', [1])
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 1)
        self.assertIsInstance(res[0], dict)
        self.assertEqual(res[0]['id'], 1)
