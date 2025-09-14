package exp2;

import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpExchange;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.rmi.Naming;

public class AuthHttpBridge {
    public static void main(String[] args) throws Exception {
        AuthService auth = (AuthService) Naming.lookup("rmi://localhost/AuthService");

        HttpServer server = HttpServer.create(new InetSocketAddress(5000), 0);
        server.createContext("/login", (HttpExchange exchange) -> {
            if ("POST".equals(exchange.getRequestMethod())) {
                String body = new String(exchange.getRequestBody().readAllBytes());
                // body like: user=alice&pass=alice123
                String[] parts = body.split("&");
                String user = parts[0].split("=")[1];
                String pass = parts[1].split("=")[1];

                String token = auth.login(user, pass);
                String response;
                if (token != null) {
                    response = "{\"success\":true, \"token\":\"" + token + "\"}";
                } else {
                    response = "{\"success\":false}";
                }

                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, response.length());
                try (OutputStream os = exchange.getResponseBody()) {
                    os.write(response.getBytes());
                }
            } else {
                exchange.sendResponseHeaders(405, -1);
            }
        });

        System.out.println("Auth HTTP bridge running at http://localhost:5000/login");
        server.start();
    }
}
