package pw.model;

import java.io.Serializable;

public record AgencyOffer(
        String agencyName,
        String hotelProvider,
        int hotelPriceEur,
        String flightProvider,
        int flightPriceEur,
        int serviceFeeEur,
        int totalPriceEur
) implements Serializable {
}