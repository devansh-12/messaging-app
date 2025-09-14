package exp2;

import java.rmi.Naming;

public class AuthClient {
    public static void main(String[] args) {
        try {
            if (args.length < 2) {
                System.err.println("usage: AuthClient <username> <password>");
                System.exit(2);
            }
            String u = args[0], p = args[1];
            AuthService svc = (AuthService) Naming.lookup("rmi://localhost/AuthService");
            String token = svc.login(u, p);
            if (token == null) {
                System.out.println("AUTH_FAIL");
                System.exit(1);
            } else {
                System.out.println(token);
                System.exit(0);
            }
        } catch (Exception e) {
            System.out.println("AUTH_ERROR");
            System.exit(3);
        }
    }
}
