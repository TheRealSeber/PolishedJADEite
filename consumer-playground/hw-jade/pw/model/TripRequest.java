package pw.model;

import java.io.Serializable;
import java.time.LocalDate;

public record TripRequest(
        String fromCity,
        String toCity,
        LocalDate departDate,
        LocalDate returnDate
) implements Serializable {
}