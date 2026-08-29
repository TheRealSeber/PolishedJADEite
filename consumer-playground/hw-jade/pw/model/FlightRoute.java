package pw.model;

import java.io.Serializable;
import java.time.LocalDate;
import java.util.Objects;

public final class FlightRoute implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String fromCity;
    private final String toCity;
    private final LocalDate date;
    private final int priceEur;

    public FlightRoute(String fromCity, String toCity, LocalDate date, int priceEur) {
        this.fromCity = fromCity;
        this.toCity = toCity;
        this.date = date;
        this.priceEur = priceEur;
    }

    public String fromCity() { return fromCity; }
    public String toCity() { return toCity; }
    public LocalDate date() { return date; }
    public int priceEur() { return priceEur; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof FlightRoute)) return false;
        FlightRoute that = (FlightRoute) o;
        return priceEur == that.priceEur
                && Objects.equals(fromCity, that.fromCity)
                && Objects.equals(toCity, that.toCity)
                && Objects.equals(date, that.date);
    }

    @Override
    public int hashCode() {
        return Objects.hash(fromCity, toCity, date, priceEur);
    }

    @Override
    public String toString() {
        return "FlightRoute[fromCity=" + fromCity + ", toCity=" + toCity
                + ", date=" + date + ", priceEur=" + priceEur + "]";
    }
}