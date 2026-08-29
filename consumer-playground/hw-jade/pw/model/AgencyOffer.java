package pw.model;

import java.io.Serializable;
import java.util.Objects;

public final class AgencyOffer implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String agencyName;
    private final String hotelProvider;
    private final int hotelPriceEur;
    private final String flightProvider;
    private final int flightPriceEur;
    private final int serviceFeeEur;
    private final int totalPriceEur;

    public AgencyOffer(String agencyName, String hotelProvider, int hotelPriceEur,
                       String flightProvider, int flightPriceEur,
                       int serviceFeeEur, int totalPriceEur) {
        this.agencyName = agencyName;
        this.hotelProvider = hotelProvider;
        this.hotelPriceEur = hotelPriceEur;
        this.flightProvider = flightProvider;
        this.flightPriceEur = flightPriceEur;
        this.serviceFeeEur = serviceFeeEur;
        this.totalPriceEur = totalPriceEur;
    }

    public String agencyName() { return agencyName; }
    public String hotelProvider() { return hotelProvider; }
    public int hotelPriceEur() { return hotelPriceEur; }
    public String flightProvider() { return flightProvider; }
    public int flightPriceEur() { return flightPriceEur; }
    public int serviceFeeEur() { return serviceFeeEur; }
    public int totalPriceEur() { return totalPriceEur; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof AgencyOffer)) return false;
        AgencyOffer that = (AgencyOffer) o;
        return hotelPriceEur == that.hotelPriceEur
                && flightPriceEur == that.flightPriceEur
                && serviceFeeEur == that.serviceFeeEur
                && totalPriceEur == that.totalPriceEur
                && Objects.equals(agencyName, that.agencyName)
                && Objects.equals(hotelProvider, that.hotelProvider)
                && Objects.equals(flightProvider, that.flightProvider);
    }

    @Override
    public int hashCode() {
        return Objects.hash(agencyName, hotelProvider, hotelPriceEur,
                flightProvider, flightPriceEur, serviceFeeEur, totalPriceEur);
    }

    @Override
    public String toString() {
        return "AgencyOffer[agencyName=" + agencyName + ", hotelProvider=" + hotelProvider
                + ", hotelPriceEur=" + hotelPriceEur + ", flightProvider=" + flightProvider
                + ", flightPriceEur=" + flightPriceEur + ", serviceFeeEur=" + serviceFeeEur
                + ", totalPriceEur=" + totalPriceEur + "]";
    }
}