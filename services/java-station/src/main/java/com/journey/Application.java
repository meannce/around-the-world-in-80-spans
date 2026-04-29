package com.journey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import java.util.*;

@SpringBootApplication
@RestController
public class Application {

    private final RestTemplate rest = new RestTemplate();

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @PostMapping("/journey")
    public ResponseEntity<Map<String, Object>> journey(
            @RequestBody Map<String, Object> journey,
            @RequestHeader HttpHeaders incomingHeaders) {

        @SuppressWarnings("unchecked")
        List<String> stops = (List<String>) journey.computeIfAbsent("stops", k -> new ArrayList<>());
        stops.add("java-station");
        journey.put("hop", ((Number) journey.getOrDefault("hop", 0)).intValue() + 1);

        String nextStop = System.getenv().getOrDefault("NEXT_STOP", "http://dotnet-station:5001/journey");

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            // propagate W3C trace context (OTel Java agent handles this automatically
            // via RestTemplate instrumentation when -javaagent is active)
            if (incomingHeaders.containsKey("traceparent")) {
                headers.put("traceparent", incomingHeaders.get("traceparent"));
            }
            if (incomingHeaders.containsKey("tracestate")) {
                headers.put("tracestate", incomingHeaders.get("tracestate"));
            }
            rest.exchange(nextStop, HttpMethod.POST,
                new HttpEntity<>(journey, headers), String.class);
        } catch (Exception e) {
            System.err.println("forward error: " + e.getMessage());
        }

        return ResponseEntity.ok(Map.of("status", "passed", "service", "java-station", "stops", stops));
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
