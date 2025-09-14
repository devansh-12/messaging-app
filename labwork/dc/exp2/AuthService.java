package exp2;

import java.rmi.Remote;
import java.rmi.RemoteException;

public interface AuthService extends Remote {
    // Returns a simple token if valid, else null
    String login(String username, String password) throws RemoteException;
}
