"""Objects for implementing location objects."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


class Location(object):
    """Object representing a geographic location."""

    def __init__(self, lat_deg=None, long_deg=None, location=None):
        """Return a Location instance created with the passed in latitude and longitude."""
        if location is not None:
            (self.lat_deg, self.long_deg) = location
        elif lat_deg is not None and long_deg is not None:
            self.lat_deg = float(lat_deg)
            self.long_deg = float(long_deg)

    @classmethod
    def from_objs(cls, lat_obj, long_obj):
        """Return a Location instance created with the passed in latitude object and longitude object."""
        return cls(lat_obj.to_degrees(), long_obj.to_degrees())

    @classmethod
    def google_maps_url(cls, lat_str, long_str):
        """Given a latitude and longitude, return a Google Maps URL for that location."""
        return f'"http://maps.google.com/?ie=UTF8&q=" || {lat_str} || "," || {long_str} || "&z=13"'

    def to_google_maps_url(self):
        """Return a Google Maps URL for the location."""
        return self.google_maps_url(self.lat_deg, self.long_deg)

    def __eq__(self, other):
        if not isinstance(other, Location):
            return NotImplemented
        return (self.lat_deg == other.lat_deg) and (self.long_deg == other.long_deg)

    def __repr__(self):
        return f'Location({self.lat_deg}, {self.long_deg})'

    def __str__(self):
        return self.__repr__()
