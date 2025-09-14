package exp2;

import java.rmi.registry.LocateRegistry;
import java.rmi.Naming;

public class AuthServer {
    public static void main(String[] args) {
        try {
            LocateRegistry.createRegistry(1099); // default RMI registry
            AuthServiceImpl svc = new AuthServiceImpl();
            Naming.rebind("rmi://localhost/AuthService", svc);
            System.out.println("RMI AuthService up at rmi://localhost/AuthService");
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}

