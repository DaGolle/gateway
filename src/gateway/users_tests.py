'''
Tests for the users module.

Created on Sep 22, 2012

@author: fryckbos
'''
import unittest
import time
import os

from users import UserController

class UserControllerTest(unittest.TestCase):
    """ Tests for UserController. """

    FILE = "test.db"
    
    def setUp(self): #pylint: disable-msg=C0103
        """ Run before each test. """
        if os.path.exists(UserControllerTest.FILE):
            os.remove(UserControllerTest.FILE)
    
    def tearDown(self): #pylint: disable-msg=C0103
        """ Run after each test. """
        if os.path.exists(UserControllerTest.FILE):
            os.remove(UserControllerTest.FILE)

    def __get_controller(self):
        """ Get a UserController using FILE. """
        return UserController(UserControllerTest.FILE,
                              { 'username' : 'om', 'password' : 'pass' }, 10)

    def test_empty(self):
        """ Test an empty database. """
        user_controller = self.__get_controller()
        self.assertEquals(None, user_controller.login("fred", "test"))
        self.assertEquals(False, user_controller.check_token("some token 123"))
        self.assertEquals(None, user_controller.get_role("fred"))
    
        token = user_controller.login("om", "pass")
        self.assertNotEquals(None, token)
        
        self.assertTrue(user_controller.check_token(token))
    
    def test_all(self):
        """ Test all methods of UserController. """
        user_controller = self.__get_controller()
        user_controller.create_user("fred", "test", "admin", True)
        
        self.assertEquals(None, user_controller.login("fred", "123"))
        self.assertFalse(user_controller.check_token("blah"))
        
        token = user_controller.login("fred", "test")
        self.assertNotEquals(None, token)
        
        self.assertTrue(user_controller.check_token(token))
        self.assertFalse(user_controller.check_token("blah"))
        
        self.assertEquals("admin", user_controller.get_role("fred"))
    
    def test_token_timeout(self):
        """ Test the timeout on the tokens. """
        user_controller = UserController(UserControllerTest.FILE,
                              { 'username' : 'om', 'password' : 'pass' }, 3)
        
        token = user_controller.login("om", "pass")
        self.assertNotEquals(None, token)
        self.assertTrue(user_controller.check_token(token))
        
        time.sleep(4)
        
        self.assertFalse(user_controller.check_token(token))
        
        token = user_controller.login("om", "pass")
        self.assertNotEquals(None, token)
        self.assertTrue(user_controller.check_token(token))
    
    def test_get_usernames(self):
        """ Test getting all usernames. """
        user_controller = self.__get_controller()
        self.assertEquals([ "om" ], user_controller.get_usernames())
        
        user_controller.create_user("test", "test", "admin", True)
        self.assertEquals([ "om", "test" ], user_controller.get_usernames())
    
    def test_remove_user(self):
        """ Test removing a user. """
        user_controller = self.__get_controller()
        self.assertEquals([ "om" ], user_controller.get_usernames())
        
        user_controller.create_user("test", "test", "admin", True)
        
        token = user_controller.login("test", "test")
        self.assertTrue(user_controller.check_token(token))
        
        user_controller.remove_user("test")
        
        self.assertFalse(user_controller.check_token(token))
        self.assertEquals([ "om" ], user_controller.get_usernames())
        
        try:
            user_controller.remove_user("om")
            self.fail("Should have raised exception !")
        except Exception as e:
            self.assertEquals("Cannot delete last admin account", str(e))
        
if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
