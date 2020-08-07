

def test():
  def A():
      print("A")
      B()

  def B():
      print("B")
      A()

  A()

test()