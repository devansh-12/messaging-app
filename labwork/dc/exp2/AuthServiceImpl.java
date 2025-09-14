package exp2;

import java.rmi.server.UnicastRemoteObject;
import java.rmi.RemoteException;
import java.util.*;

public class AuthServiceImpl extends UnicastRemoteObject implements AuthService {
    private final Map<String, String> users = new HashMap<>();

    protected AuthServiceImpl() throws RemoteException {
        super();
        // demo users
        users.put("alice", "alice123");
        users.put("bob", "bob123");
        users.put("admin", "admin123");
    }

    @Override
    public String login(String username, String password) throws RemoteException {
        if (users.containsKey(username) && Objects.equals(users.get(username), password)) {
            return "token_" + username + "_" + System.currentTimeMillis();
        }
        return null;
    }
}

